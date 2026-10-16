import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.io.*;
import java.lang.reflect.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import javax.net.ssl.*;

/** Independent offline review probes. Never uses an external transport. */
public class AuditProbe {
    static final ObjectMapper JSON = new ObjectMapper();
    static Path out;
    static int rankPageNumber;
    static final Map<String,Object> results = new LinkedHashMap<>();
    static final String VTRADE = "{\"id\":\"cursor-1\",\"tradeOrderId\":991,\"symbol\":\"EURUSD.sc\",\"baseSymbol\":\"EURUSD\",\"tradeAction\":\"BUY\",\"volume\":0.1,\"openTime\":1789984800000,\"closeTime\":1789988400000,\"openPrice\":1.1,\"closePrice\":1.2,\"closeNetPnl\":-25}";
    static final String ZTRADE = "{\"tradeId\":991,\"currency\":\"EUR/USD\",\"tradeType\":\"BUY\",\"lots\":0.1,\"dateOpen\":1789984800000,\"dateClosed\":1789988400000,\"priceOpen\":1.1,\"priceClosed\":1.2,\"netPnl\":-25,\"grossPnl\":-24,\"pips\":-10}";
    static final String PTR = "{\"TradeId\":\"audit-991\",\"Instrument\":\"EURUSD\",\"Direction\":\"Buy\",\"Quantity\":0.1,\"OpenPrice\":1.1,\"ClosePrice\":1.2,\"OpenTimestamp\":\"2026-09-21T10:00:00\",\"CloseTimestamp\":\"2026-09-21T11:00:00\",\"RealisedProfit\":-25,\"CurrencyCode\":\"USD\",\"ServerCode\":\"audit\"}";

    public static void main(String[] args) throws Exception {
        out = Path.of(args[0]); Files.createDirectories(out);
        vantage(); zulu(); pelican();
        for(String repo:List.of("vantage","zulumonitor")) { runner(repo,false); runner(repo,true); }
        JSON.writerWithDefaultPrettyPrinter().writeValue(out.resolve("results.json").toFile(),results);
        System.out.println(JSON.writerWithDefaultPrettyPrinter().writeValueAsString(results));
    }

    static Object call(Object target,String name,Object...args) throws Exception {
        Class<?> c = target instanceof Class<?> cl ? cl : target.getClass();
        for(Method m:c.getMethods()) if(m.getName().equals(name)&&m.getParameterCount()==args.length) {
            try { return m.invoke(target instanceof Class<?> ? null:target,args); }
            catch(IllegalArgumentException mismatch) { continue; }
            catch(InvocationTargetException e) { if(e.getCause() instanceof Exception x)throw x;throw e; }
        }
        throw new NoSuchMethodException(c+"."+name);
    }
    static Object internal(Object target,String name,Class<?>[] types,Object...args) throws Exception {
        Method m=target.getClass().getDeclaredMethod(name,types);m.setAccessible(true);
        try{return m.invoke(target,args);}catch(InvocationTargetException e){if(e.getCause() instanceof Exception x)throw x;throw e;}
    }
    static String pkg(String repo) {return "de."+(repo.equals("PelicanTrading")?"pelicanmonitor":repo.equals("vantage")?"vantagemonitor":"zulumonitor");}
    static Object clsNew(String name,Class<?>[] types,Object...args)throws Exception{return Class.forName(name).getConstructor(types).newInstance(args);}
    static void check(boolean v,String what){if(!v)throw new AssertionError(what);}
    static int freePort()throws Exception{try(var socket=new ServerSocket(0)){return socket.getLocalPort();}}
    static void mockHttp(Object target,FakeHttp client)throws Exception{Field f=target.getClass().getDeclaredField("http");f.setAccessible(true);f.set(target,client);}

    static void vantage() throws Exception {
        String p=pkg("vantage");Path data=out.resolve("vantage-data");
        var provider=de.vantagemonitor.api.VantageClient.parseFilterSignal(JSON.readTree("{\"strategyId\":970101,\"strategyName\":\"Synthetic Vantage\",\"currency\":\"USD\",\"copiers\":1,\"maxDrawDown\":-0.1,\"returnRate\":0.05}"));
        provider.setMonths(12);
        var zero=de.vantagemonitor.api.VantageClient.parseFilterSignal(JSON.readTree("{\"strategyId\":970102,\"strategyName\":\"Synthetic zero\",\"currency\":\"USD\",\"copiers\":0}"));
        new de.vantagemonitor.store.DataStore(data).saveSignals(List.of(provider,zero));
        ObjectNode row=(ObjectNode)JSON.readTree(VTRADE);row.remove("closeNetPnl");row.remove("tradeAction");
        var trade=de.vantagemonitor.api.VantageClient.parseTrade(row,false);
        check(trade.getNetPnl()==0,"missing Vantage PnL converted to 0");
        new de.vantagemonitor.store.TradeStore(data).saveTrades(970101,List.of(trade),List.of(),List.of(),1);
        results.put("vantage_missing_pnl_parsed",trade.getNetPnl());
        provider.setReturnRatePctAll(50);
        var losing=de.vantagemonitor.api.VantageClient.parseTrade(JSON.readTree(VTRADE),false);
        Double badDd=de.vantagemonitor.report.SignalPayloadBuilder.tradeDdAusTrades(provider,List.of(losing));
        results.put("vantage_negative_dd_basis",Map.of("realised_pnl",-25,"lifetime_return_pct",50,"implied_basis",-50,"returned_dd",badDd));
        check(badDd==0,"invalid negative DD basis returned as 0");
        var cfg=new de.vantagemonitor.rest.RestApiConfig();cfg.setPort(freePort());cfg.setInstanceName("audit-vantage");
        var server=new de.vantagemonitor.rest.RestApiServer(data,cfg,(de.vantagemonitor.rest.UpdateStarter)starter(p),()->{throw new IOException("offline audit: FX forbidden");});
        server.starten();try{endpoints("vantage",server.port(),970101,"vantage",cfg);}finally{server.stoppen();}
        var client=new de.vantagemonitor.api.VantageClient(0);
        FakeHttp transport=new FakeHttp(r -> r.uri().getPath().contains("history-list")
            ? "{\"code\":200,\"data\":{\"currency\":\"USD\",\"totalCount\":2,\"orderList\":["+VTRADE+"]}}"
            : "{\"code\":200,\"data\":{\"orderList\":[]}}" );
        mockHttp(client,transport);
        var bundle=client.downloadTrades(provider,3,null);
        results.put("vantage_repeated_cursor",Map.of("rows",bundle.history().size(),"unique_trade_ids",bundle.history().stream().map(t->t.getTradeOrderId()).distinct().count(),"reported_total",bundle.totalCount(),"requests",transport.requests));
        check(bundle.history().size()==3 && bundle.history().stream().map(t->t.getTradeOrderId()).distinct().count()==1,"duplicate cursor is accepted");
        FakeHttp rank=new FakeHttp(r -> r.uri().getPath().contains("topLists")?"{\"code\":200,\"data\":{\"topTraders\":[]}}":rankPage());
        mockHttp(client,rank);var ranked=client.downloadProviders(200,null);
        results.put("vantage_union_default_target",Map.of("rows",ranked.size(),"requests",rank.requests));
        check(rank.requests.stream().noneMatch(s->s.contains("overallSort=1")),"default target never queries return ranking");
    }
    static String rankPage()throws Exception {int offset=100*rankPageNumber++;ArrayNode list=JSON.createArrayNode();for(int i=1;i<=100;i++)list.addObject().put("strategyId",970000+offset+i).put("copiers",1).put("strategyName","Synthetic "+i);return "{\"code\":200,\"data\":"+list+"}";}

    static void zulu()throws Exception {
        String p=pkg("zulumonitor");Path data=out.resolve("zulu-data");
        var client=new de.zulumonitor.api.ZuluTradeClient(0);
        var provider=(de.zulumonitor.model.Trader)internal(client,"parseTrader",new Class[]{JsonNode.class},JSON.readTree(zProvider(970201,1)));
        var zero=(de.zulumonitor.model.Trader)internal(client,"parseTrader",new Class[]{JsonNode.class},JSON.readTree(zProvider(970202,0)));
        new de.zulumonitor.store.DataStore(data).saveTraders(List.of(provider,zero));
        ObjectNode node=(ObjectNode)JSON.readTree(ZTRADE);node.remove("netPnl");node.remove("tradeType");
        var trade=(de.zulumonitor.model.Trade)internal(client,"parseTrade",new Class[]{JsonNode.class,int.class},node,970201);
        var valid=client.getClass().getDeclaredMethod("gueltigerTradeDatensatz",JsonNode.class);valid.setAccessible(true);
        results.put("zulu_missing_pnl_validation",Map.of("accepted",valid.invoke(null,node),"pnl",trade.getNetPnl()));
        check((boolean)valid.invoke(null,node) && trade.getNetPnl()==0,"missing Zulu pnl accepted as zero");
        var losing=(de.zulumonitor.model.Trade)internal(client,"parseTrade",new Class[]{JsonNode.class,int.class},JSON.readTree(ZTRADE),970201);
        Double badDd=de.zulumonitor.report.TradePayloadBuilder.tradeDdAusTrades(provider,List.of(losing));
        results.put("zulu_negative_dd_basis",Map.of("realised_pnl",-25,"lifetime_return_pct",50,"implied_basis",-50,"returned_dd",badDd));
        check(badDd==0,"invalid negative DD basis returned as 0");
        new de.zulumonitor.store.DataStore(data).saveTrades(970201,List.of(trade),Integer.MAX_VALUE);
        var cfg=new de.zulumonitor.rest.RestApiConfig();cfg.setPort(freePort());cfg.setInstanceName("audit-zulu");
        var server=new de.zulumonitor.rest.RestApiServer(data,cfg,(de.zulumonitor.rest.UpdateStarter)starter(p),()->{throw new IOException("offline audit: FX forbidden");});
        server.starten();try{endpoints("zulumonitor",server.port(),970201,"zulu",cfg);}finally{server.stoppen();}
        FakeHttp transport=new FakeHttp(r->"{\"content\":["+ZTRADE+"],\"last\":false}");mockHttp(client,transport);
        var repeated=client.downloadTradeHistory(970201,3,(a,b,c)->{});
        results.put("zulu_repeated_pages",Map.of("rows",repeated.size(),"unique_trade_ids",repeated.stream().map(t->t.getTradeId()).distinct().count()));
        check(repeated.size()==3&&repeated.stream().map(t->t.getTradeId()).distinct().count()==1,"Zulu repeated pages accepted");
    }
    static String zProvider(int id,int followers){return "{\"providerId\":"+id+",\"profile\":{\"name\":\"Synthetic Zulu\",\"baseCurrencyName\":\"USD\"},\"overallStats\":{\"followers\":"+followers+",\"weeks\":52,\"roiProfit\":50,\"overallDrawDownPercent\":-10},\"timeframeStats\":{\"10000\":{\"trades\":1,\"maxDrawDownPercent\":-10}}}";}

    static void pelican()throws Exception {
        Path data=out.resolve("pelican-data");String p=pkg("PelicanTrading");
        var client=new de.pelicanmonitor.api.PelicanClient("http://audit.invalid",null,0);
        FakeHttp transport=new FakeHttp(r->"[{\"Strategy\":{\"Id\":970301,\"Name\":\"Synthetic Pelican\",\"NumCopiers\":1}},{\"Strategy\":{\"Id\":970302,\"Name\":\"Synthetic zero\",\"NumCopiers\":0}}]");mockHttp(client,transport);
        var providers=client.ladeAlleProvider();providers.get(0).setCurrencyCode("USD");providers.get(1).setCurrencyCode("USD");
        providers.get(0).setInception(LocalDate.of(2025,9,21));providers.get(0).setTradesTotal(1);
        new de.pelicanmonitor.store.DataStore(data).saveProviders(providers);
        mockHttp(client,new FakeHttp(r->"["+PTR+"]"));
        var trades=client.ladeGeschlosseneSignale(970301,LocalDate.of(2026,9,21),LocalDate.of(2026,9,21),(a,b,c)->{});
        var store=new de.pelicanmonitor.store.SignalStore(data.resolve("signals"));store.saveClosed(970301,trades);
        var oldDate=LocalDateTime.of(2026,9,21,10,0);
        var gain=new de.pelicanmonitor.model.Signal("audit-gain","970301","EURUSD","Buy",0.1,1.1,oldDate,"audit","USD",1.2,oldDate.plusHours(1),250.0,null,null,null,null,null);
        var loss=new de.pelicanmonitor.model.Signal("audit-loss","970301","EURUSD","Buy",0.1,1.1,oldDate.plusDays(1),"audit","USD",1.2,oldDate.plusDays(1).plusHours(1),-50.0,null,null,null,null,null);
        var cashModel=new de.pelicanmonitor.model.Provider(970301);cashModel.setReturnInceptionPct(10.0);
        double staleDd=de.pelicanmonitor.report.ReportService.tradeDdAusTrades(cashModel,List.of(gain,loss),List.of());
        cashModel.setReturnInceptionPct(20.0);double alignedDd=de.pelicanmonitor.report.ReportService.tradeDdAusTrades(cashModel,List.of(gain,loss),List.of());
        results.put("pelican_cached_stats_fresh_trades_dd",Map.of("final_realised_pnl",200,"stale_return_pct",10,"fresh_return_pct",20,"stale_dd",staleDd,"aligned_dd",alignedDd));
        Files.createDirectories(data.resolve("reports"));Files.writeString(data.resolve("reports/bericht_970301_audit.md"),"Synthetic audit report");
        var cfg=new de.pelicanmonitor.rest.RestApiConfig();cfg.setPort(freePort());cfg.setInstanceName("audit-pelican");
        var server=new de.pelicanmonitor.rest.RestApiServer(data,cfg,(currency)->{throw new IOException("offline audit: FX forbidden");},(de.pelicanmonitor.rest.UpdateStarter)starter(p),()->{throw new IOException("offline audit: FX forbidden");});
        server.starten();try{endpoints("PelicanTrading",server.port(),970301,"pelican",cfg);}finally{server.stoppen();}
        cfg.setToken("");
        mockHttp(client,new FakeHttp(r->"[{\"error\":\"schema changed\"}]"));
        var schemaEmpty=client.ladeAlleProvider();results.put("pelican_nonempty_wrong_schema_catalogue",Map.of("received_rows",1,"parsed_rows",schemaEmpty.size(),"exception",false));
        check(schemaEmpty.isEmpty(),"wrong array entries silently become empty catalogue");
        ObjectNode bad=(ObjectNode)JSON.readTree(PTR);bad.remove("RealisedProfit");mockHttp(client,new FakeHttp(r->"["+bad+"]"));
        var missing=client.ladeGeschlosseneSignale(970301,LocalDate.of(2026,9,21),LocalDate.of(2026,9,21),(a,b,c)->{});
        check(missing.getFirst().getRealisedProfit()==null,"Pelican preserves null PnL");
        store.saveClosed(970301,missing);
        var second=new de.pelicanmonitor.rest.RestApiServer(data,cfg,(currency)->{throw new IOException("offline");},null,()->{throw new IOException("offline");});
        second.starten();try{var r=get(second.port(),"/providers/970301/pelican/trades.csv");results.put("pelican_missing_pnl_export",Map.of("status",r.statusCode(),"body",r.body()));check(r.statusCode()==404,"Pelican must reject unknown pnl");}finally{second.stoppen();}
    }

    static Object starter(String p)throws Exception {
        Class<?> iface=Class.forName(p+".rest.UpdateStarter");
        Object job=clsNew(p+".update.UpdateJob",new Class[]{String.class},"synthetic-job");call(job,"melde","katalog",0,1,"audit running");
        Class<?> response=Class.forName(p+".rest.UpdateStarter$UpdateAntwort");
        return java.lang.reflect.Proxy.newProxyInstance(iface.getClassLoader(),new Class[]{iface},(o,m,args)->m.getName().equals("letzterJob")?job:response.getMethod("gestartet",job.getClass()).invoke(null,job));
    }
    static HttpResponse<String> get(int port,String path)throws Exception{return HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/v1"+path)).GET().build(),HttpResponse.BodyHandlers.ofString());}
    static void endpoints(String repo,int port,int id,String version,Object cfg)throws Exception {
        List<Map<String,Object>> matrix=new ArrayList<>();
        for(String path:List.of("/health","/providers","/providers?minSubscribers=0","/providers?limit=1&offset=1","/providers?offset=2147483647","/providers/"+id,"/providers/"+id+"/"+version+"/history","/providers/"+id+"/"+version+"/metrics","/providers/"+id+"/"+version+"/trades","/providers/"+id+"/"+version+"/trades.csv","/providers/"+id+"/"+version+"/reports","/providers/"+id+"/wrong/metrics","/providers/999999999/"+version+"/metrics","/update/status")) {
            var r=get(port,path);matrix.add(Map.of("method","GET","path",path,"status",r.statusCode(),"body",r.body()));
            if(path.endsWith("/trades.csv"))Files.writeString(out.resolve(repo+".csv"),r.body(),StandardCharsets.UTF_8);
        }
        var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/v1/update")).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString("{\"target\":2,\"tradelisten\":true}")).build();
        var post=HttpClient.newHttpClient().send(request,HttpResponse.BodyHandlers.ofString());matrix.add(Map.of("method","POST","path","/update","status",post.statusCode(),"body",post.body()));
        check(post.statusCode()==202,"synthetic update202");
        if(repo.equals("PelicanTrading")) {
            var report=get(port,"/providers/"+id+"/"+version+"/reports/bericht_"+id+"_audit.md");
            matrix.add(Map.of("method","GET","path","/reports/{whitelisted_name}","status",report.statusCode(),"body",report.body()));check(report.statusCode()==200,"whitelisted report download");
            var traversal=get(port,"/providers/"+id+"/"+version+"/reports/%2e%2e%2fproviders.csv");
            matrix.add(Map.of("method","GET","path","/reports/{encoded_traversal}","status",traversal.statusCode(),"body",traversal.body()));check(traversal.statusCode()==404,"report traversal refused");
        }
        call(cfg,"setToken","audit-token");
        for(String mode:List.of("missing","X-API-Token","Bearer","query","OPTIONS","POST")) {
            var b=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/v1"+(mode.equals("POST")?"/update":"/health")+(mode.equals("query")?"?token=audit-token":"")));
            if(mode.equals("X-API-Token"))b.header(mode,"audit-token");
            if(mode.equals("Bearer"))b.header("Authorization","Bearer audit-token");
            if(mode.equals("OPTIONS"))b.method("OPTIONS",HttpRequest.BodyPublishers.noBody());else if(mode.equals("POST"))b.POST(HttpRequest.BodyPublishers.ofString("{}"));else b.GET();
            var r=HttpClient.newHttpClient().send(b.build(),HttpResponse.BodyHandlers.ofString());
            matrix.add(Map.of("method",mode,"path","token_probe","status",r.statusCode(),"body",r.body()));
            check(r.statusCode()==(mode.equals("OPTIONS")?204:mode.equals("missing")||mode.equals("POST")?401:200),"token mode "+mode);
        }
        results.put(repo+"_endpoint_matrix",matrix);
        String csv=Files.readString(out.resolve(repo+".csv"));check(csv.contains("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit"),"scanner header");
    }

    static void runner(String repo,boolean skip)throws Exception {
        String p=pkg(repo);Class<?> iface=Class.forName(p+".update.UpdateJobRunner$Dienste");
        final int id=skip?(repo.equals("vantage")?970101:970201):970401;
        Object provider=repo.equals("vantage")?de.vantagemonitor.api.VantageClient.parseFilterSignal(JSON.readTree("{\"strategyId\":"+id+",\"currency\":\"USD\",\"copiers\":1}"))
            :internal(new de.zulumonitor.api.ZuluTradeClient(0),"parseTrader",new Class[]{JsonNode.class},JSON.readTree(zProvider(id,1)));
        final boolean actualPredicate;
        if(skip&&repo.equals("vantage")) {
            Path data=out.resolve("vantage-data");var trades=new de.vantagemonitor.store.TradeStore(data);
            var ledger=new de.vantagemonitor.store.TradeListStore(data.resolve("tradelisten"));
            ledger.save(id,trades.loadTrades(id),de.vantagemonitor.store.TradeListStore.shaVonTrades(trades.loadTrades(id)));
            Files.setLastModifiedTime(trades.tradesFile(id),java.nio.file.attribute.FileTime.from(Instant.parse("2020-01-01T00:00:00Z")));
            actualPredicate=ledger.istGeladen(id)&&(trades.hasTrades(id)||ledger.hasCached(id));
        } else if(skip) {
            Path data=out.resolve("zulu-data");var trades=new de.zulumonitor.store.DataStore(data);
            var ledger=new de.zulumonitor.store.TradeListenStore(data.resolve("tradelisten"));
            String sha=trades.verifiedSha256(id);ledger.markiereGeladen(id,sha);
            Files.setLastModifiedTime(trades.getTradesDir().resolve("trades_"+id+".csv"),java.nio.file.attribute.FileTime.from(Instant.parse("2020-01-01T00:00:00Z")));
            actualPredicate=ledger.istFrisch(id,sha)&&trades.hasTrades(id,Integer.MAX_VALUE);
        } else actualPredicate=false;
        if(skip)check(actualPredicate,"real app cache predicate accepts arbitrarily old cache");
        int[] attempts={0};
        Object svc=java.lang.reflect.Proxy.newProxyInstance(iface.getClassLoader(),new Class[]{iface},(o,m,a)->{
            switch(m.getName()) {
                case "ladeSignale":case "gespeicherteSignale":case "ladeTrader":case "gespeicherteTrader":return List.of(provider);
                case "tradelisteBereitsGeladen":case "tradelisteFrischGeladen":return actualPredicate;
                case "ladeTradeliste":attempts[0]++;throw new IOException("synthetic failed download");
                case "gespeicherterSha":return "";
                default:return null;
            }
        });
        Object job=clsNew(p+".update.UpdateJob",new Class[]{String.class},"audit-"+(skip?"skip":"failure"));
        Object runner=clsNew(p+".update.UpdateJobRunner",new Class[]{job.getClass(),iface,Path.class,int.class,boolean.class,int.class},job,svc,out.resolve(repo+"-runner-"+skip),200,true,0);
        call(runner,"run");results.put(repo+"_runner_"+(skip?"old_verified_cache_skip":"failed_download"),Map.of("attempts",attempts[0],"status",call(job,"statusJson")));
        check(attempts[0]==(skip?0:1),"runner download count");
    }

    /** An in-memory HTTP transport, so even fixed production API URLs stay offline. */
    static final class FakeHttp extends HttpClient {
        interface Reply {String reply(HttpRequest request)throws Exception;}
        final Reply reply;final List<String> requests=new ArrayList<>();
        FakeHttp(Reply reply){this.reply=reply;}
        @Override @SuppressWarnings("unchecked") public <T> HttpResponse<T> send(HttpRequest req,HttpResponse.BodyHandler<T> handler)throws IOException {
            String label=req.method()+" "+req.uri().getPath()+"?"+req.uri().getQuery();
            if(req.bodyPublisher().isPresent()) {
                var bytes=new ByteArrayOutputStream();CompletableFuture<Void> done=new CompletableFuture<>();
                req.bodyPublisher().get().subscribe(new java.util.concurrent.Flow.Subscriber<java.nio.ByteBuffer>() {
                    public void onSubscribe(java.util.concurrent.Flow.Subscription s){s.request(Long.MAX_VALUE);}
                    public void onNext(java.nio.ByteBuffer b){while(b.hasRemaining())bytes.write(b.get());}
                    public void onError(Throwable t){done.completeExceptionally(t);}public void onComplete(){done.complete(null);}
                });done.join();String body=bytes.toString(StandardCharsets.UTF_8);if(body.contains("overallSort"))label+=" overallSort="+JSON.readTree(body).path("overallSort").asText();
            }
            requests.add(label);String body;try{body=reply.reply(req);}catch(Exception e){throw new IOException(e);}
            final String finalBody=body;
            return new HttpResponse<T>() {
                public int statusCode(){return 200;} public HttpRequest request(){return req;}public Optional<HttpResponse<T>> previousResponse(){return Optional.empty();}
                public HttpHeaders headers(){return HttpHeaders.of(Map.of("Content-Type",List.of("application/json")),(a,b)->true);}
                public T body(){return (T)finalBody;}public Optional<SSLSession> sslSession(){return Optional.empty();}public URI uri(){return req.uri();}public Version version(){return Version.HTTP_1_1;}
            };
        }
        public <T> CompletableFuture<HttpResponse<T>> sendAsync(HttpRequest r,HttpResponse.BodyHandler<T>b){throw new UnsupportedOperationException("offline");}
        public <T> CompletableFuture<HttpResponse<T>> sendAsync(HttpRequest r,HttpResponse.BodyHandler<T>b,HttpResponse.PushPromiseHandler<T>p){throw new UnsupportedOperationException("offline");}
        public Optional<CookieHandler> cookieHandler(){return Optional.empty();}public Optional<Duration> connectTimeout(){return Optional.empty();}public Redirect followRedirects(){return Redirect.NEVER;}
        public Optional<ProxySelector> proxy(){return Optional.empty();}public SSLContext sslContext(){try{return SSLContext.getDefault();}catch(Exception e){throw new RuntimeException(e);}}
        public SSLParameters sslParameters(){return new SSLParameters();}public Optional<Authenticator> authenticator(){return Optional.empty();}public Version version(){return Version.HTTP_1_1;}public Optional<Executor> executor(){return Optional.empty();}
    }
}
