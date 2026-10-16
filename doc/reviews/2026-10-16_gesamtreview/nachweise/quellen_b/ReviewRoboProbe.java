package de.robomonitor.rest;

import com.fasterxml.jackson.databind.ObjectMapper;
import de.robomonitor.api.RoboForexClient;
import de.robomonitor.deals.TradeAggregator;
import de.robomonitor.model.Deal;
import de.robomonitor.model.SignalAccount;
import de.robomonitor.model.Trade;
import de.robomonitor.store.DataStore;
import de.robomonitor.store.DealStore;
import de.robomonitor.update.UpdateJob;
import de.robomonitor.update.UpdateJobRunner;
import de.robomonitor.report.SignalPayloadBuilder;
import java.lang.reflect.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;

/** Independent synthetic audit only. Does not contact any platform. */
public class ReviewRoboProbe {
  static final ObjectMapper JSON = new ObjectMapper();
  static final LocalDateTime T = LocalDateTime.of(2026, 1, 2, 12, 0);
  static Deal deal(long id, long pos, String entry, double lots, double price, double profit) {
    Deal d = new Deal("mt5", id);
    d.setPositionId(pos); d.setEntry(entry); d.setSymbol("EURUSD");
    d.setSide(entry.equals("IN") ? "BUY" : "SELL");
    d.setLots(lots); d.setPrice(price); d.setOpenTime(T.plusHours(id));
    d.setProfit(profit); d.setNetPnl(profit);
    return d;
  }
  static Map<String,Object> trade(List<Deal> deals) {
    List<Trade> ts = TradeAggregator.zuTrades(deals);
    Map<String,Object> o = new LinkedHashMap<>();
    o.put("trades", ts.size()); o.put("openPositions", TradeAggregator.offenePositionen(deals));
    o.put("totalNet", ts.stream().mapToDouble(Trade::getNetPnl).sum());
    if (!ts.isEmpty()) {
      Trade t = ts.get(0);
      o.put("lots", t.getLots()); o.put("open", String.valueOf(t.getOpenTime()));
      o.put("close", String.valueOf(t.getCloseTime())); o.put("openPrice", t.getOpenPrice());
      o.put("closePrice", t.getClosePrice()); o.put("net", t.getNetPnl());
      o.put("csv", RestApiServer.mql5Zeile(t));
    }
    return o;
  }
  static Object invoke(RestApiServer server, String name, long id) throws Exception {
    Method m = RestApiServer.class.getDeclaredMethod(name, long.class); m.setAccessible(true);
    Object resp = m.invoke(server, id);
    Map<String,Object> result = new LinkedHashMap<>();
    for (String f : List.of("status", "body", "json")) {
      Field field = resp.getClass().getDeclaredField(f); field.setAccessible(true);
      result.put(f, field.get(resp));
    }
    return result;
  }
  public static void main(String[] args) throws Exception {
    Path root = Path.of(args[0]); Files.createDirectories(root);
    Map<String,Object> out = new LinkedHashMap<>();
    List<Deal> partial = List.of(deal(1, 10, "IN", 1, 1.1, 0), deal(2, 10, "OUT", .25, 1.11, 25));
    out.put("partial_expected_remaining_apiLots_0_75", trade(partial));
    out.put("two_outs_expected_remaining_apiLots_0_5", trade(List.of(partial.get(0), partial.get(1), deal(3,10,"OUT",.25,1.12,25))));
    out.put("orphan_unknown_open", trade(List.of(deal(4, 20, "OUT", .1, 1.11, -25))));
    out.put("netting_reversal", trade(List.of(deal(1,30,"IN",1,1.1,0),deal(2,30,"INOUT",2,1.12,200),deal(3,30,"OUT",1,1.11,100))));
    String missing = "[{\"ticket\":1,\"cmd\":0,\"symbol\":\"EURUSD\",\"volume\":100000,\"open_time\":\"2026-01-01T12:00:00Z\",\"close_time\":\"2026-01-02T12:00:00Z\",\"open_price\":1.1,\"close_price\":1.11}]";
    List<Deal> unknownProfit = RoboForexClient.parseMt4Deals(JSON.readTree(missing));
    out.put("missing_profit", trade(unknownProfit));
    SignalAccount ddAccount = new SignalAccount("synthetic",102);
    ddAccount.setProfitPercent(10); ddAccount.setYieldPeriodMonths(0);
    Deal deposit=new Deal("mt4",80);deposit.setSide("BALANCE");deposit.setOpenTime(T);deposit.setNetPnl(1000);
    Deal win=new Deal("mt4",81);win.setSide("BUY");win.setSymbol("EURUSD");win.setOpenTime(T.plusHours(1));win.setCloseTime(T.plusHours(2));win.setNetPnl(100);
    Deal loss=new Deal("mt4",82);loss.setSide("BUY");loss.setSymbol("EURUSD");loss.setOpenTime(T.plusHours(3));loss.setCloseTime(T.plusHours(4));loss.setNetPnl(-50);
    List<Deal> withDeposit=List.of(deposit,win,loss);
    out.put("closing_dd_same_data_with_balance",Map.of(
      "fromDeals",SignalPayloadBuilder.tradeDdAusDeals(ddAccount,withDeposit),
      "fromTrades",SignalPayloadBuilder.tradeDdAusTrades(ddAccount,TradeAggregator.zuTrades(withDeposit)),
      "dealsWithoutDeposit",SignalPayloadBuilder.tradeDdAusDeals(ddAccount,List.of(win,loss))));
    SignalAccount s = new SignalAccount("synthetic", 101); s.setName("Synthetic");
    s.setPlatform("mt5"); s.setSubscriberCount(2); s.setBalanceUsd(1000);
    new DataStore(root).saveSignals(List.of(s));
    DealStore store = new DealStore(root);
    store.saveDeals(101,"mt5","synthetic",partial,0,0);
    RestApiServer rest = new RestApiServer(root, new RestApiConfig());
    out.put("partial_rest", invoke(rest,"tradesCsv",101));
    Files.writeString(root.resolve("partial_trades.csv"), "\ufeffTime;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"+RestApiServer.mql5Zeile(TradeAggregator.zuTrades(partial).get(0))+"\n");
    Files.writeString(root.resolve("orphan_trades.csv"), "\ufeffTime;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"+RestApiServer.mql5Zeile(TradeAggregator.zuTrades(List.of(deal(4,20,"OUT",.1,1.11,-25))).get(0))+"\n");
    // A self-consistent signed CSV can still contain a malformed row: hash is no parse guarantee.
    Deal bad = deal(5,40,"OUT",1,1.1,-100); bad.setSide("SELL;BROKEN");
    store.saveDeals(101,"mt5","synthetic",List.of(partial.get(0),bad),0,0);
    out.put("signed_semantically_invalid_cache", Map.of("hasDeals",store.hasDeals(101),"storedRows",2,"loadedRows",store.loadDeals(101).size(),"response",invoke(rest,"tradesCsv",101)));
    // Snapshot checksum cannot establish time freshness; future jobs use this exact predicate.
    store.saveDeals(101,"mt5","synthetic",partial,0,0);
    Method mark=DealStore.class.getMethod("merkGeladen",long.class,String.class);
    mark.invoke(store,101,store.shaVon(101));
    Path meta=root.resolve("deals/deals_101.meta");
    Files.writeString(meta,Files.readString(meta).replaceAll("fetched_at=.*","fetched_at=2020-01-01T00:00:00Z"));
    out.put("old_cache_still_fresh",store.istFrischGeladen(101));
    List<SignalAccount> accounts=new ArrayList<>();
    for(int i=0;i<6;i++){SignalAccount a=new SignalAccount("synthetic",200+i);a.setName("Synthetic "+i);a.setPlatform("mt5");accounts.add(a);}
    final int[] failedCalls={0};
    UpdateJobRunner.Dienste services=(UpdateJobRunner.Dienste) Proxy.newProxyInstance(ReviewRoboProbe.class.getClassLoader(),new Class[]{UpdateJobRunner.Dienste.class},(proxy,method,vals)->{
      return switch(method.getName()) {
        case "hatCookies" -> true;
        case "ladeSignale", "gespeicherteSignale" -> accounts;
        case "hatTagesliste", "dealsFrischGeladen" -> false;
        case "ladeTagesliste", "ladeDeals" -> {failedCalls[0]++;throw new java.io.IOException("synthetic unavailable");}
        case "dealSha" -> "synthetic";
        default -> null;
      };
    });
    UpdateJob j=new UpdateJob("synthetic-errors");
    new UpdateJobRunner(j,services,root.resolve("update_errors"),6,true,0).run();
    out.put("failed_download_calls",failedCalls[0]);out.put("all_downloads_failed_job",j.statusJson());
    Files.writeString(root.resolve("probe_results.json"),JSON.writerWithDefaultPrettyPrinter().writeValueAsString(out));
    System.out.println(JSON.writerWithDefaultPrettyPrinter().writeValueAsString(out));
  }
}
