package rest;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import converter.HtmlConverter;
import config.ConfigurationManager;
import downloader.SignalDownloader;
import org.openqa.selenium.WebDriver;
/** Synthetic parser/CSV contract audit without browser or external requests. */
public class ReviewMqlProbe {
  public static void main(String[] args) throws Exception {
    Method parse=RestApiServer.class.getDeclaredMethod("parseUpdateBody",String.class);parse.setAccessible(true);
    for(String input:List.of("NOT JSON", "{\"target\":1.5,\"tradelisten\":\"false\"}", "{\"target\":99999999999999999999999}", "{\"tradelisten\":false}")) {
      try{System.out.println(input+" -> "+parse.invoke(null,input));}
      catch(InvocationTargetException e){System.out.println(input+" -> "+e.getCause());}
    }
    UpdateJob job=new UpdateJob("synthetic");job.ergebnis("signaleGeliefert",2);job.hinweis("synthetic warning");job.fertig("2026-01-01T12:00:00");
    Method write=RestApiServer.class.getDeclaredMethod("jsonVon",Map.class);write.setAccessible(true);
    System.out.println("update status serialized="+write.invoke(null,job.statusJson()));
    Path p=Path.of(args[0]);Files.createDirectories(p);
    Files.writeString(p.resolve("normal_mql5.csv"),"\ufeffTime;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n2026.01.01 12:00:00;Buy;0.1;EURUSD;1.1;0.1;2026.01.02 12:00:00;1.11;-2;-1;100\n");
    Files.writeString(p.resolve("normal_mql4.csv"),"\ufeffTime;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n2026.01.01 12:00:00;Buy;0.1;EURUSD;1.1;1.0;1.2;2026.01.02 12:00:00;1.11;-2;-1;100;synthetic\n");
    Path conversion=p.resolve("conversion");Files.createDirectories(conversion);
    Files.writeString(conversion.resolve("conversionLog.txt"),"synthetic audit\n");
    Path html=conversion.resolve("Synthetic_101_root.html"), csv=conversion.resolve("Synthetic_101.csv"),txt=conversion.resolve("Synthetic_101_root.txt");
    Files.writeString(html,"<html><head><title>Synthetic</title></head><body>upstream DOM changed: no monthly fields</body></html>");
    Files.writeString(csv,Files.readString(p.resolve("normal_mql5.csv")));
    Files.writeString(txt,"Balance=1000\nEquityDrawdown=10\n");
    HtmlConverter converter=new HtmlConverter(conversion.toString());
    Method convert=HtmlConverter.class.getDeclaredMethod("convertHtmlFile",Path.class);convert.setAccessible(true);
    convert.invoke(converter,html);
    System.out.println("missing monthly data after conversion: html="+Files.exists(html)+", csv="+Files.exists(csv)+", txt="+Files.exists(txt));
    CsvParser parsed=CsvParser.parse(p.resolve("normal_mql5.csv").toFile());
    System.out.println("normal MT5 JSON header="+parsed.getHeader()+", row="+parsed.getRows().get(0));
    Path configRoot=p.resolve("prefix_config");Files.createDirectories(configRoot.resolve("config"));
    ConfigurationManager config=new ConfigurationManager(configRoot.toString());
    config.setDownloadPath(configRoot.resolve("download").toString());
    config.setDownloadDays(5);
    WebDriver stub=(WebDriver) Proxy.newProxyInstance(ReviewMqlProbe.class.getClassLoader(),new Class[]{WebDriver.class},(proxy,method,vals)->null);
    SignalDownloader downloader=new SignalDownloader(stub,config,config.getCredentials());
    Path target=Path.of(config.getCurrentDownloadPath());
    if(!target.toAbsolutePath().normalize().startsWith(p.toAbsolutePath().normalize()))throw new IllegalStateException("audit path escaped");
    Files.createDirectories(target);
    Files.writeString(target.resolve("Alpha_101_root.html"),"<html>synthetic</html>");
    Files.writeString(target.resolve("AlphaOther_999.csv"),Files.readString(p.resolve("normal_mql5.csv")));
    Method recent=SignalDownloader.class.getDeclaredMethod("isFileRecentlyDownloaded",String.class,String.class);recent.setAccessible(true);
    System.out.println("no Alpha_101.csv, unrelated AlphaOther_999.csv only -> recent="+recent.invoke(downloader,"101","Alpha"));
  }
}
