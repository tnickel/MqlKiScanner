package zulu.audit;

import java.io.*;
import java.lang.instrument.*;
import java.lang.reflect.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.objectweb.asm.*;

/** One-shot, exact-job guard for the old Zulu lifecycle, not a general kill tool. */
public final class GuardAgent {
    private static volatile boolean armed;
    private static volatile Thread target;
    private static volatile String jobId;
    private static Path report;
    private static final Set<Integer> blocked = ConcurrentHashMap.newKeySet();

    public static void agentmain(String config, Instrumentation instrumentation) {
        Thread controller = new Thread(() -> {
            try { run(Path.of(config), instrumentation); }
            catch (Throwable problem) { event("FAILED", problem.toString()); }
        }, "zulu-guarded-cancel-controller");
        controller.setDaemon(false);
        controller.start();
    }

    public static void beforeWrite(int providerId) throws IOException {
        if (armed && Thread.currentThread() == target) {
            if (blocked.add(providerId)) event("PUBLICATION_BLOCKED", Integer.toString(providerId));
            throw new IOException("Manueller Abbruch: Publikation vor jedem Dateischreiben gesperrt");
        }
    }

    public static void beforeAnyDataWrite() throws IOException {
        if (armed && Thread.currentThread() == target)
            throw new IOException("Manueller Abbruch: DataStore-Schreibschutz aktiv");
    }

    public static void beforeFinish(Object job) throws Exception {
        if (!armed || !jobId.equals(job.getClass().getMethod("jobId").invoke(job))) return;
        Method result = job.getClass().getMethod("ergebnis", String.class, Object.class);
        result.invoke(job, "tradelistenAbgebrochen", true);
        result.invoke(job, "datenstand", null);
        job.getClass().getMethod("hinweis", String.class).invoke(job,
                "Altjob manuell kooperativ abgebrochen; kein erfolgreicher Gesamtdatenstand");
        event("SUCCESS_SUPPRESSED", jobId);
        throw new CancellationException("Altjob manuell kooperativ abgebrochen; kein erfolgreicher Gesamtdatenstand");
    }

    private static synchronized void event(String phase, String detail) {
        String line = "{\"utc\":\"" + java.time.Instant.now() + "\",\"phase\":\"" + escape(phase)
                + "\",\"detail\":\"" + escape(detail) + "\"}\n";
        try {
            if (report != null) Files.writeString(report, line, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException failure) { System.err.print(line); }
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }

    private static void require(boolean test, String reason) {
        if (!test) throw new IllegalStateException(reason);
    }

    private static String hash(Path path) throws Exception {
        if (!Files.isRegularFile(path)) return "ABSENT";
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }

    private static Map<String, String> archiveHashes(Path base, List<Integer> ids) throws Exception {
        Map<String, String> hashes = new TreeMap<>();
        for (int id : ids) for (String suffix : List.of("csv", "meta")) {
            String name = "trades_" + id + "." + suffix;
            hashes.put(name, hash(base.resolve("trades").resolve(name)));
        }
        return hashes;
    }

    private static void recordHashes(Map<String, String> hashes, String suffix) throws IOException {
        StringBuilder text = new StringBuilder();
        hashes.forEach((name, value) -> text.append(value).append("  ").append(name).append('\n'));
        Files.writeString(report.resolveSibling(report.getFileName() + "." + suffix + ".sha256"),
                text, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }

    private static void locked(List<Object> locks, int i, Checked action) throws Exception {
        if (i == locks.size()) { action.run(); return; }
        synchronized (locks.get(i)) { locked(locks, i + 1, action); }
    }
    private interface Checked { void run() throws Exception; }

    private static boolean safeHttpOrPageWait(StackTraceElement[] stack) {
        boolean history = false, wait = false;
        for (StackTraceElement frame : stack) {
            if (frame.getClassName().equals("de.zulumonitor.store.DataStore")
                    && (frame.getMethodName().equals("writeVerifiedTrades") || frame.getMethodName().equals("writeAtomic")))
                return false;
            if (frame.getClassName().equals("de.zulumonitor.update.UpdateJob") && frame.getMethodName().equals("fertig"))
                return false;
            history |= frame.getClassName().equals("de.zulumonitor.api.ZuluTradeClient")
                    && frame.getMethodName().equals("downloadTradeHistory");
            wait |= frame.getClassName().startsWith("jdk.internal.net.http.") && frame.getMethodName().equals("send");
            wait |= frame.getClassName().equals("java.util.concurrent.CompletableFuture")
                    && frame.getMethodName().equals("waitingGet");
            wait |= frame.getClassName().equals("java.lang.Thread") && frame.getMethodName().equals("sleep");
        }
        return history && wait;
    }

    private static String fetch(String statusUrl) throws Exception {
        return HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(statusUrl))
                .timeout(Duration.ofSeconds(5)).GET().build(), HttpResponse.BodyHandlers.ofString()).body();
    }

    private static void run(Path config, Instrumentation inst) throws Exception {
        Properties p = new Properties();
        try (Reader in = Files.newBufferedReader(config)) { p.load(in); }
        report = Path.of(p.getProperty("report")).toAbsolutePath();
        require(!Files.exists(report), "Report already exists: no repeated attachment");
        jobId = p.getProperty("jobId");
        require(ProcessHandle.current().pid() == Long.parseLong(p.getProperty("pid")), "Unexpected JVM PID");
        Path data = Path.of(p.getProperty("dataDir")).toAbsolutePath().normalize();
        require(Path.of("data").toAbsolutePath().normalize().equals(data), "Unexpected JVM working directory");
        Path catalogue = data.resolve("traders.csv");
        String catalogueSha = p.getProperty("catalogueSha256");
        String statusUrl = p.getProperty("statusUrl");
        require(jobId != null && jobId.matches("[A-Za-z0-9_-]+"), "Invalid exact job ID");
        require(hash(catalogue).equals(catalogueSha), "Catalogue changed");
        List<Integer> ids = Arrays.stream(p.getProperty("providerIds").split(","))
                .map(Integer::parseInt).distinct().sorted().toList();
        require(!ids.isEmpty() && ids.stream().allMatch(id -> id > 0), "Invalid provider scope");
        Class<?> store = null, job = null;
        for (Class<?> type : inst.getAllLoadedClasses()) {
            if (type.getName().equals("de.zulumonitor.store.DataStore")) store = type;
            if (type.getName().equals("de.zulumonitor.update.UpdateJob")) job = type;
        }
        require(store != null && job != null, "Old classes not loaded");
        require(inst.isModifiableClass(store) && inst.isModifiableClass(job), "Classes cannot be retransformed");
        require(Modifier.isPrivate(store.getDeclaredMethod("writeVerifiedTrades", int.class, List.class, int.class).getModifiers()),
                "Unexpected old publication method");
        require(Arrays.stream(job.getDeclaredMethods()).noneMatch(m -> m.getName().equals("requestCancellation")),
                "Already fixed version: use supported Cancel API instead");
        List<Thread> workers = Thread.getAllStackTraces().keySet().stream()
                .filter(t -> t.isAlive() && t.getName().equals("update-job")).toList();
        require(workers.size() == 1, "Need exactly one old update-job thread");
        target = workers.getFirst();
        Field lockField = store.getDeclaredField("TRADE_LOCKS");
        lockField.setAccessible(true);
        @SuppressWarnings("unchecked") ConcurrentMap<Path, Object> map = (ConcurrentMap<Path, Object>) lockField.get(null);
        Set<Path> expectedKeys = new HashSet<>();
        for (int id : ids) expectedKeys.add(data.resolve("trades/trades_" + id + ".csv").normalize());
        Set<Path> priorKeys = new HashSet<>(map.keySet());
        require(priorKeys.stream().allMatch(key -> key.isAbsolute() && key.equals(key.toAbsolutePath().normalize())
                && key.getParent().equals(data.resolve("trades"))), "Unexpected existing lock namespace");
        long matchingPriorKeys = priorKeys.stream().filter(expectedKeys::contains).count();
        require(matchingPriorKeys > 0, "No pre-existing provider lock matches the configured namespace");
        event("EXISTING_LOCK_NAMESPACE_VERIFIED", "matchingProviderKeys=" + matchingPriorKeys);
        List<Object> locks = ids.stream().map(id -> map.computeIfAbsent(
                data.resolve("trades/trades_" + id + ".csv").normalize(), ignored -> new Object())).toList();
        Class<?> finalStore = store, finalJob = job;
        final Map<String, String>[] baseline = new Map[]{null};
        final boolean[] installed = {false};
        event("PREFLIGHT", "providers=" + ids.size() + "; thread=" + target.threadId());
        long installDeadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
        while (!installed[0] && target.isAlive() && System.nanoTime() < installDeadline) {
            locked(locks, 0, () -> {
                if (!safeHttpOrPageWait(target.getStackTrace())) return;
                require(hash(catalogue).equals(catalogueSha), "Catalogue changed before guard");
                String state = fetch(statusUrl);
                require(state.contains("\"jobId\":\"" + jobId + "\"") || state.contains("\"jobId\": \"" + jobId + "\""), "Job changed");
                require(state.contains("\"state\":\"running\"") || state.contains("\"state\": \"running\""), "Job no longer running");
                baseline[0] = archiveHashes(data, ids);
                recordHashes(baseline[0], "before");
                int fixtureRaceDelay = Integer.parseInt(p.getProperty("fixtureRaceDelayMs", "0"));
                if (fixtureRaceDelay > 0) {
                    require("fixture".equals(p.getProperty("mode")), "Race hooks allowed only in fixture");
                    event("LOCKS_HELD_FIXTURE_RACE", "all provider locks held; HTTP may return before retransform");
                    Thread.sleep(fixtureRaceDelay);
                }
                // All possible provider commits are excluded while the new,
                // synchronous write boundary and finish guard are installed.
                GuardTransformer transformer = new GuardTransformer(finalStore, finalJob,
                        p.getProperty("expectedStoreShape"), p.getProperty("expectedJobShape"));
                inst.addTransformer(transformer, true);
                try {
                    inst.retransformClasses(finalStore, finalJob);
                    // Transformer exceptions can be ignored by Instrumentation.
                    // A returned, generated guard for BOTH classes is mandatory.
                    require(transformer.generated.equals(Set.of(finalStore, finalJob)), "Both guards were not generated");
                    require(transformer.failure == null, "Guard transformer failed: " + transformer.failure);
                    armed = true;
                }
                catch (Throwable failure) { armed = false; throw failure; }
                finally { inst.removeTransformer(transformer); }
                installed[0] = true;
                event("GUARD_INSTALLED", "archiveFiles=" + baseline[0].size()
                        + "; allProviderLocksHeld=true; activePublicationFrame=false");
            });
            if (!installed[0]) Thread.sleep(25);
        }
        require(installed[0], "No safe history HTTP/page-wait phase observed; no interrupt performed");
        long deadline = System.nanoTime() + Duration.ofMinutes(5).toNanos();
        int fixtureInterruptDelay = Integer.parseInt(p.getProperty("fixtureInterruptDelayMs", "0"));
        if (fixtureInterruptDelay > 0) {
            require("fixture".equals(p.getProperty("mode")), "Delay hook allowed only in fixture");
            Thread.sleep(fixtureInterruptDelay);
        }
        int interrupts = 0;
        while (target.isAlive() && System.nanoTime() < deadline) {
            if (safeHttpOrPageWait(target.getStackTrace())) {
                target.interrupt();
                interrupts++;
                event("HTTP_INTERRUPT", Integer.toString(interrupts));
                target.join(50);
            } else target.join(25);
        }
        require(!target.isAlive(), "Worker did not finish; write guard remains installed, no process close allowed");
        Map<String, String> after = archiveHashes(data, ids);
        recordHashes(after, "after");
        require(baseline[0].equals(after), "Archive bytes changed despite guard; no process close allowed");
        String terminal = fetch(statusUrl);
        require(terminal.contains("\"state\":\"error\"") || terminal.contains("\"state\": \"error\""), "Missing explicit error terminal state");
        require(terminal.contains("\"tradelistenAbgebrochen\":true") || terminal.contains("\"tradelistenAbgebrochen\": true"), "Missing aborted diagnostic");
        require(terminal.contains("\"datenstand\":null") || terminal.contains("\"datenstand\": null"), "False successful data timestamp");
        event("WORKER_ENDED_ARCHIVES_IDENTICAL", "interrupts=" + interrupts + "; blockedProviders=" + blocked.size()
                + "; state=error; aborted=true; dataTimestamp=null");
        // No Platform.exit, no window close and no process termination here.
        // A separate lifecycle step may close only after verifying this result.
    }

    private static final class GuardTransformer implements ClassFileTransformer {
        private final Class<?> store, job;
        private final String storeShape, jobShape;
        final Set<Class<?>> generated = new HashSet<>();
        volatile Throwable failure;
        GuardTransformer(Class<?> store, Class<?> job, String storeShape, String jobShape) {
            this.store = store; this.job = job; this.storeShape = storeShape; this.jobShape = jobShape;
        }
        @Override public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> redefined, ProtectionDomain domain, byte[] bytes) {
            if (redefined != store && redefined != job) return null;
            try {
            String shape = ClassShape.of(bytes);
            event("LOADED_CLASS_SHAPE", name + "; normalizedSha256=" + shape);
            require(shape.equals(redefined == store ? storeShape : jobShape), "Loaded class differs from tested old code: " + name);
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            int[] guarded = {0};
            reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
                @Override public MethodVisitor visitMethod(int access, String method, String desc,
                        String signature, String[] exceptions) {
                    MethodVisitor original = super.visitMethod(access, method, desc, signature, exceptions);
                    String hook = null;
                    if (redefined == store && method.equals("writeVerifiedTrades")
                            && desc.equals("(ILjava/util/List;I)Ljava/lang/String;")) hook = "beforeWrite";
                    if (redefined == store && method.equals("writeAtomic")) hook = "beforeAnyDataWrite";
                    if (redefined == job && method.equals("fertig") && desc.equals("(Ljava/lang/String;)V")) hook = "beforeFinish";
                    if (hook == null) return original;
                    guarded[0]++;
                    String selected = hook;
                    return new MethodVisitor(Opcodes.ASM9, original) {
                        @Override public void visitCode() {
                            super.visitCode();
                            if (selected.equals("beforeWrite")) {
                                visitVarInsn(Opcodes.ILOAD, 1);
                                visitMethodInsn(Opcodes.INVOKESTATIC, "zulu/audit/GuardAgent", selected, "(I)V", false);
                            } else if (selected.equals("beforeFinish")) {
                                visitVarInsn(Opcodes.ALOAD, 0);
                                visitMethodInsn(Opcodes.INVOKESTATIC, "zulu/audit/GuardAgent", selected, "(Ljava/lang/Object;)V", false);
                            } else visitMethodInsn(Opcodes.INVOKESTATIC, "zulu/audit/GuardAgent", selected, "()V", false);
                        }
                    };
                }
            }, 0);
            require(guarded[0] == (redefined == store ? 3 : 1), "Unexpected old method shape");
            event("CLASS_GUARDED", name + "; methods=" + guarded[0] + "; originalSha256=" + digest(bytes));
            generated.add(redefined);
            return writer.toByteArray();
            } catch (Throwable problem) {
                failure = problem;
                event("TRANSFORM_FAILED", problem.toString());
                return null;
            }
        }
    }
    private static String digest(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
