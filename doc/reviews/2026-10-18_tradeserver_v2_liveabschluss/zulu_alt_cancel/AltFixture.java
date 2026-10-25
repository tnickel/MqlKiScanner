package zulu.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import de.zulumonitor.api.ZuluTradeClient;
import de.zulumonitor.model.*;
import de.zulumonitor.store.DataStore;
import de.zulumonitor.update.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;

/** Synthetic old runner/client/store; only loopback HTTP and private temp data. */
public final class AltFixture {
    private static Trade trade(int id, long tradeId) {
        return new Trade(tradeId, id, "EUR/USD", "BUY", 0.1,
                LocalDateTime.of(2026, 9, 21, 10, 0), LocalDateTime.of(2026, 9, 21, 11, 0),
                1.1, 1.2, 1, 1, 1, 1, false);
    }
    private static Trader trader(int id) {
        return new Trader(id, "Synthetic " + id, "Germany", "Fixture", "USD",
                LocalDate.now().minusWeeks(52), false, id, 3, 1,
                42, 60, 55, -1, -17.75, 52, 1, 1, 1, 2, 1, 1, 1, -1, 1, 1785211282000L);
    }
    private static boolean seen(Path report, String text) {
        try { return Files.isRegularFile(report) && Files.readString(report).contains(text); }
        catch (IOException ignored) { return false; }
    }
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Path data = Path.of("data");
        Path report = Path.of("guard.jsonl").toAbsolutePath();
        DataStore store = new DataStore(data);
        List<Trader> traders = java.util.stream.IntStream.rangeClosed(1, 7).mapToObj(AltFixture::trader).toList();
        store.saveTraders(traders);
        for (Trader t : traders) store.saveTrades(t.getProviderId(), List.of(trade(t.getProviderId(), t.getProviderId())), 100);
        UpdateJob job = new UpdateJob("fixture-" + mode);
        ObjectMapper mapper = new ObjectMapper();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(Executors.newCachedThreadPool(r -> { Thread t = new Thread(r); t.setDaemon(true); return t; }));
        CountDownLatch firstHttp = new CountDownLatch(1), releaseHttp = new CountDownLatch(1);
        server.createContext("/api/v1/update/status", x -> {
            byte[] bytes = mapper.writeValueAsBytes(job.statusJson());
            x.sendResponseHeaders(200, bytes.length);
            try (var out = x.getResponseBody()) { out.write(bytes); }
        });
        server.createContext("/", x -> {
            firstHttp.countDown();
            try {
                if (mode.equals("return_race") || mode.equals("shape_mismatch")) {
                    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
                    String expected = mode.equals("return_race") ? "LOCKS_HELD_FIXTURE_RACE" : "FAILED";
                    while (!seen(report, expected) && System.nanoTime() < deadline) Thread.sleep(5);
                } else releaseHttp.await(30, TimeUnit.SECONDS);
                String body = "{\"content\":[{\"tradeId\":9001,\"currency\":\"EUR/USD\",\"tradeType\":\"BUY\",\"lots\":0.1,"
                        + "\"dateOpen\":1774744200000,\"dateClosed\":1774747800000,\"priceOpen\":1.1,\"priceClosed\":1.2,\"netPnl\":0}],\"last\":true}";
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                x.sendResponseHeaders(200, bytes.length);
                try (var out = x.getResponseBody()) { out.write(bytes); }
            } catch (Exception ignored) { x.close(); }
        });
        server.start();
        String host = "http://127.0.0.1:" + server.getAddress().getPort();
        ZuluTradeClient client = new ZuluTradeClient(0, host, host, HttpClient.newHttpClient());
        UpdateJobRunner.Dienste services = new UpdateJobRunner.Dienste() {
            public List<Trader> ladeTrader(int n, ZuluTradeClient.ProgressListener listener) { return traders; }
            public void speichereTrader(List<Trader> rows) { }
            public void abonnentenSnapshot(List<Trader> rows) { }
            public List<Trader> gespeicherteTrader() { return traders; }
            public boolean tradelisteFrischGeladen(int id) { return store.verifiedSha256(id) != null; }
            public List<Trade> ladeTradeliste(Trader t) throws Exception {
                return client.downloadTradeHistory(t.getProviderId(), Integer.MAX_VALUE, (c, total, msg) -> { });
            }
            public String speichereTradeliste(Trader t, List<Trade> rows) throws Exception {
                return store.mergeTrades(t.getProviderId(), rows, Integer.MAX_VALUE);
            }
            public void merkeTradelisteGeladen(int id, String sha) { if (!mode.equals("shape_mismatch")) throw new AssertionError("Unexpected ledger publication"); }
            public void speichereOffenePositionen(Trader t) { if (!mode.equals("shape_mismatch")) throw new AssertionError("Unexpected open-position publication"); }
            public void berechneTradeDd(Trader t, List<Trade> rows) { if (!mode.equals("shape_mismatch")) throw new AssertionError("Unexpected DD publication"); }
            public void traderAnzeigen(List<Trader> rows) { }
            public void log(String text) { System.out.println(text); }
        };
        Thread worker = new Thread(new UpdateJobRunner(job, services, data, 7, true, 0), "update-job");
        worker.setDaemon(true); // reproduce unsafe old application lifecycle exactly
        worker.start();
        if (!firstHttp.await(5, TimeUnit.SECONDS)) throw new AssertionError("No first HTTP request");
        Thread previousWriter = null;
        if (mode.equals("prior_writer")) {
            var lockMethod = DataStore.class.getDeclaredMethod("tradeLock", int.class);
            lockMethod.setAccessible(true);
            Object lock = lockMethod.invoke(store, 1);
            CountDownLatch owns = new CountDownLatch(1);
            previousWriter = new Thread(() -> {
                synchronized (lock) {
                    owns.countDown();
                    try {
                        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
                        while (!seen(report, "PREFLIGHT") && System.nanoTime() < deadline) Thread.sleep(5);
                        store.mergeTrades(1, List.of(trade(1, 8001)), 100);
                        Files.writeString(Path.of("prior_writer.completed"), "true");
                    } catch (Exception e) { throw new RuntimeException(e); }
                }
            }, "fixture-prior-publisher");
            previousWriter.start();
            if (!owns.await(2, TimeUnit.SECONDS)) throw new AssertionError("Prior writer missing");
        }
        Properties config = new Properties();
        config.setProperty("mode", "fixture");
        config.setProperty("pid", Long.toString(ProcessHandle.current().pid()));
        config.setProperty("dataDir", data.toAbsolutePath().toString());
        config.setProperty("report", report.toString());
        config.setProperty("jobId", job.jobId());
        config.setProperty("catalogueSha256", java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(data.resolve("traders.csv")))));
        config.setProperty("providerIds", "1,2,3,4,5,6,7");
        config.setProperty("statusUrl", host + "/api/v1/update/status");
        Properties shapes = new Properties();
        try (Reader in = Files.newBufferedReader(Path.of("shapes.properties"))) { shapes.load(in); }
        config.setProperty("expectedStoreShape", shapes.getProperty("expectedStoreShape"));
        config.setProperty("expectedJobShape", shapes.getProperty("expectedJobShape"));
        if (mode.equals("shape_mismatch")) config.setProperty("expectedStoreShape", "WRONG_SHAPE_MUST_NOT_INTERRUPT");
        if (mode.equals("return_race")) {
            config.setProperty("fixtureRaceDelayMs", "200");
            config.setProperty("fixtureInterruptDelayMs", "300");
        }
        try (Writer out = Files.newBufferedWriter(Path.of("attach.properties"))) { config.store(out, "synthetic fixture only"); }
        Files.writeString(Path.of("ready"), Long.toString(ProcessHandle.current().pid()));
        worker.join(30_000);
        if (worker.isAlive()) throw new AssertionError("Worker did not end");
        if (previousWriter != null) previousWriter.join(5_000);
        if (mode.equals("shape_mismatch")) {
            if (!seen(report, "FAILED") || seen(report, "HTTP_INTERRUPT") || seen(report, "GUARD_INSTALLED"))
                throw new AssertionError("Mismatching old code must never arm or interrupt");
            if (job.state() != UpdateJob.State.DONE) throw new AssertionError("Uncancelled fixture should complete naturally");
            Files.writeString(Path.of("outcome.json"), mapper.writerWithDefaultPrettyPrinter().writeValueAsString(job.statusJson()));
            releaseHttp.countDown(); server.stop(0);
            System.out.println("FIXTURE PASS " + mode);
            return;
        }
        long guardDeadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        while (!seen(report, "WORKER_ENDED_ARCHIVES_IDENTICAL") && System.nanoTime() < guardDeadline) Thread.sleep(10);
        if (!seen(report, "WORKER_ENDED_ARCHIVES_IDENTICAL")) throw new AssertionError("Guard verification missing");
        if (job.state() != UpdateJob.State.ERROR) throw new AssertionError("False successful job");
        Map<String, Object> outcome = job.statusJson();
        if (!Boolean.TRUE.equals(((Map<?, ?>) outcome.get("ergebnis")).get("tradelistenAbgebrochen"))) throw new AssertionError("Missing abort flag");
        if (((Map<?, ?>) outcome.get("ergebnis")).get("datenstand") != null) throw new AssertionError("False successful timestamp");
        if (mode.equals("return_race") && !seen(report, "PUBLICATION_BLOCKED")) throw new AssertionError("Return race not exercised");
        if (mode.equals("prior_writer") && !Files.isRegularFile(Path.of("prior_writer.completed"))) throw new AssertionError("Prior writer did not complete");
        for (Trader t : traders) if (store.verifiedSha256(t.getProviderId()) == null) throw new AssertionError("Broken archive pair");
        Files.writeString(Path.of("outcome.json"), mapper.writerWithDefaultPrettyPrinter().writeValueAsString(outcome));
        releaseHttp.countDown(); server.stop(0);
        System.out.println("FIXTURE PASS " + mode);
    }
}
