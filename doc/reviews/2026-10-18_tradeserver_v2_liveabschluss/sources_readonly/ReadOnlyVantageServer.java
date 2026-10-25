import com.fasterxml.jackson.databind.ObjectMapper;
import de.vantagemonitor.model.SignalProvider;
import de.vantagemonitor.model.TradeRecord;
import de.vantagemonitor.rest.RestApiConfig;
import de.vantagemonitor.rest.RestApiServer;
import de.vantagemonitor.store.CopierDb;
import de.vantagemonitor.store.DataStore;
import de.vantagemonitor.store.TradeStore;
import java.nio.file.*;
import java.net.*;
import java.net.http.*;
import java.time.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

/** Temporary read-only listener; never instantiates GUI, API downloader or UpdateStarter. */
public final class ReadOnlyVantageServer {
 private static final ObjectMapper JSON=new ObjectMapper();
 public static void main(String[] args) throws Exception {
  if(args.length==2 && args[0].equals("--self-test")){selfTest(Path.of(args[1]));return;}
  if(args.length!=3)throw new IllegalArgumentException("dataDir stopFile readyFile required");
  serve(Path.of(args[0]),Path.of(args[1]),Path.of(args[2]));
 }
 public static void serve(Path requestedData,Path requestedStop,Path requestedReady) throws Exception {
  Path data=requestedData.toRealPath(),stop=requestedStop.toAbsolutePath().normalize(),ready=requestedReady.toAbsolutePath().normalize();
  if(Files.exists(stop)||Files.exists(ready))throw new IllegalStateException("Control files already exist");
  Path configFile=data.resolve("rest_api.json");
  if(Files.exists(configFile)&&(!Files.isRegularFile(configFile)||!JSON.readTree(configFile.toFile()).isObject()))throw new IllegalStateException("Present REST settings must be valid");
  RestApiConfig config=RestApiConfig.laden(configFile);
  if(!config.isEnabled())throw new IllegalStateException("Existing REST settings are disabled");
  RestApiServer server=new RestApiServer(data,config,null);
  Thread hook=new Thread(server::stoppen,"readonly-vantage-normal-shutdown");
  Runtime.getRuntime().addShutdownHook(hook);
  try {
   server.starten();
   Files.createDirectories(ready.getParent());
   JSON.writerWithDefaultPrettyPrinter().writeValue(ready.toFile(),Map.of("utc",Instant.now().toString(),"pid",ProcessHandle.current().pid(),"port",server.port(),"instance",config.getInstanceName(),"mode","GET_OPTIONS_only","updateStarter",false,"gui",false));
   while(!Files.exists(stop))Thread.sleep(100);
  } finally {
   server.stoppen();
   try{Runtime.getRuntime().removeShutdownHook(hook);}catch(IllegalStateException ignored){}
   JSON.writerWithDefaultPrettyPrinter().writeValue(ready.resolveSibling(ready.getFileName()+".stopped.json").toFile(),Map.of("utc",Instant.now().toString(),"pid",ProcessHandle.current().pid(),"stopped_normally",true,"running",server.laeuft()));
  }
 }
 private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 private static String hash(Path p) throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p)));}
 private static Map<String,String> baseline(Path data) throws Exception {
  Map<String,String> result=new TreeMap<>();try(var files=Files.walk(data)){for(Path p:files.filter(Files::isRegularFile).toList())result.put(data.relativize(p).toString(),hash(p));}return result;
 }
 private static HttpResponse<String> request(HttpClient http,int port,String path,String method) throws Exception {
  var b=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/v1"+path)).timeout(Duration.ofSeconds(5)).header("X-API-Token","fixture-only");
  if(method.equals("POST"))b.POST(HttpRequest.BodyPublishers.ofString("{}"));else if(method.equals("PUT"))b.PUT(HttpRequest.BodyPublishers.ofString("{}"));else b.GET();
  return http.send(b.build(),HttpResponse.BodyHandlers.ofString());
 }
 private static TradeRecord trade(long recordId){var t=LocalDateTime.of(2026,9,21,10,0);return new TradeRecord("GER40ft","GER40FT","BUY",.1,t,t.plusHours(1),20000.,20001.,.1,77,recordId);}
 private static void selfTest(Path report) throws Exception {
  Path root=Files.createTempDirectory(report.toAbsolutePath().getParent(),"readonly_vantage_fixture_");Path data=Files.createDirectories(root.resolve("data"));
  var provider=new SignalProvider(7);provider.setName("synthetic immutable FT");provider.setCurrency("USD");provider.setCopiers(1);provider.setTradesTotalAvailable(1L);provider.setReturnRatePctAll(20);
  new DataStore(data).saveSignals(List.of(provider));var store=new TradeStore(data);store.saveCompleteTrades(7,List.of(trade(101)),List.of(),List.of(),1);
  try(var ignored=new CopierDb(data)){}try(var ignored=new CopierDb(data)){}
  int port;try(var socket=new java.net.ServerSocket(0)){port=socket.getLocalPort();}
  var config=new RestApiConfig();config.setPort(port);config.setToken("fixture-only");config.setInstanceName("readonly-fixture");config.speichern(data.resolve("rest_api.json"));
  Map<String,String> before=baseline(data);byte[] original=Files.readAllBytes(store.tradesFile(7));Path stop=root.resolve("stop"),ready=root.resolve("ready.json");
  AtomicReference<Throwable> failure=new AtomicReference<>();Thread serverThread=new Thread(()->{try{serve(data,stop,ready);}catch(Throwable e){failure.set(e);}},"isolated-readonly-server");serverThread.start();
  HttpClient http=HttpClient.newHttpClient();
  try {
   long deadline=System.nanoTime()+Duration.ofSeconds(10).toNanos();while(!Files.exists(ready)&&failure.get()==null&&System.nanoTime()<deadline)Thread.sleep(20);
   check(failure.get()==null&&Files.exists(ready),"read-only server did not start");
   check(request(http,port,"/health","GET").statusCode()==200,"health");
   check(request(http,port,"/providers/7","GET").statusCode()==200,"provider owner");
   check(request(http,port,"/providers/7/vantage/trades.csv","GET").body().lines().count()==2,"one exact trade export");
   check(request(http,port,"/update","POST").statusCode()==405,"update POST must be disabled");
   check(request(http,port,"/providers","POST").statusCode()==405,"all other POST disabled");
   check(request(http,port,"/providers","PUT").statusCode()==405,"PUT disabled");
   check(request(http,port,"/update/status","GET").statusCode()==404,"no hidden update lifecycle");
   check(before.equals(baseline(data)),"read-only requests changed source files");
   Thread otherWriter=new Thread(()->{try{for(int i=0;i<10;i++)new TradeStore(data).saveCompleteTrades(8,List.of(trade(200+i)),List.of(),List.of(),1);}catch(Throwable e){failure.set(e);}},"unrelated-provider-writer");otherWriter.start();
   for(int i=0;i<20;i++)check(request(http,port,"/providers/7/vantage/trades.csv","GET").statusCode()==200,"unrelated writer changed immutable export");
   otherWriter.join(10000);check(!otherWriter.isAlive()&&failure.get()==null,"unrelated writer failure");
   check(Arrays.equals(original,Files.readAllBytes(store.tradesFile(7))),"immutable source was changed");
   Files.writeString(store.tradesFile(7),"\nbroken",StandardOpenOption.APPEND);
   check(request(http,port,"/providers/7/vantage/trades.csv","GET").statusCode()==404,"invalid CSV/meta must fail closed");
   Files.write(store.tradesFile(7),original);
  } finally {Files.writeString(stop,"normal stopfile request");serverThread.join(10000);}
  check(!serverThread.isAlive()&&failure.get()==null,"normal stop failed");
  try(var socket=new java.net.ServerSocket(port)){check(socket.isBound(),"port not free after stop");}
  JSON.writerWithDefaultPrettyPrinter().writeValue(report.toFile(),Map.of("tested_utc",Instant.now().toString(),"synthetic_data_only",true,"health_and_owner_get",true,"post_update_405",true,"put_405",true,"update_status_404",true,"source_bytes_unchanged_by_get",true,"unrelated_provider_writer_isolated",true,"invalid_pair_404",true,"normal_stop_and_port_free",true));
  System.out.println("Read-only Vantage fixture: all checks passed");
 }
}
