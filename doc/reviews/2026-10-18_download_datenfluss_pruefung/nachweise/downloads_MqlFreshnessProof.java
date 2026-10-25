import gui.MqlDownloaderGui;
import gui.LogHandler;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import rest.UpdateJob;
import sun.misc.Unsafe;

/** Isolated proof: no GUI constructor, downloader, browser or network call.
 *  Runs the actual precompiled update method in a sandbox working directory.
 */
class downloads_MqlFreshnessProof {
    static class SilentLog extends LogHandler {
        @Override public void log(String text) { }
    }
    public static void main(String[] args) throws Exception {
        System.setProperty("java.awt.headless", "true");
        Field unsafeField = Unsafe.class.getDeclaredField("theUnsafe");
        unsafeField.setAccessible(true);
        Unsafe unsafe = (Unsafe) unsafeField.get(null);
        // Allocation alone cannot initialize or start the application.
        MqlDownloaderGui gui = (MqlDownloaderGui) unsafe.allocateInstance(MqlDownloaderGui.class);
        Field log = MqlDownloaderGui.class.getDeclaredField("logHandler");
        log.setAccessible(true);
        log.set(gui, unsafe.allocateInstance(SilentLog.class));
        // A download attempt would fail immediately: managers remain null.
        Path marker = Path.of("config", "update_state.json");
        Files.createDirectories(marker.getParent());
        Files.writeString(marker, "katalogLetzterLoad=" + Instant.now().minusSeconds(3600) + "\n");
        UpdateJob job = new UpdateJob("isolated-audit");
        Method method = MqlDownloaderGui.class.getDeclaredMethod("starteUpdateKaskade", UpdateJob.class, int.class);
        method.setAccessible(true);
        method.invoke(gui, job, 72);
        if (job.state() != UpdateJob.State.DONE) throw new AssertionError(job.statusJson());
        System.out.println("actual_compiled_method=starteUpdateKaskade");
        System.out.println("fresh_marker_age_hours=1; configured_window_hours=72");
        System.out.println("download_manager=null; conversion_manager=null; gui_constructor_called=false");
        System.out.println("actual_job=" + job.statusJson());
        System.out.println("CONFIRMED: done without any catalogue OR trade download attempt");
    }
}
