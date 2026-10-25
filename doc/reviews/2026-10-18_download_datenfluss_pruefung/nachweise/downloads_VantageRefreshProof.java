import de.vantagemonitor.model.TradeRecord;
import de.vantagemonitor.store.TradeStore;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.List;

/** Synthetic legacy fixture against actual deployed TradeStore.class, no API calls. */
class downloads_VantageRefreshProof {
    public static void main(String[] args) throws Exception {
        Path sandbox = Path.of("downloads_vantage_sandbox");
        TradeStore store = new TradeStore(sandbox);
        LocalDateTime time = LocalDateTime.of(2026, 10, 1, 10, 0);
        TradeRecord original = new TradeRecord("EURUSD", "EURUSD", "BUY", 0.1,
                time, time.plusHours(1), 1.1, 1.2, 10.0, 1);
        TradeRecord fresh = new TradeRecord("EURUSD", "EURUSD", "BUY", 0.1,
                time.plusDays(1), time.plusDays(1).plusHours(1), 1.1, 1.2, 20.0, 2);
        store.saveTrades(7, List.of(original), List.of(), List.of(), 1);
        Path file = sandbox.resolve("trades/trades_7.csv");
        Path meta = sandbox.resolve("trades/trades_7.meta");
        Files.writeString(meta, Files.readString(meta).replace("version=2", "version=1").replace("timeBasis=UTC\n", ""));
        String before = Files.readString(file);
        if (store.hasTrades(7)) throw new AssertionError("Legacy unexpectedly accepted");
        try {
            store.mergeHistory(7, List.of(fresh));
            throw new AssertionError("Unexpected successful legacy merge");
        } catch (IOException expected) {
            System.out.println("actual_mergeHistory_error=" + expected.getMessage());
        }
        try {
            store.saveTrades(7, List.of(fresh), List.of(), List.of(), 1);
            throw new AssertionError("Unexpected successful legacy refresh");
        } catch (IOException expected) {
            System.out.println("actual_saveTrades_error=" + expected.getMessage());
        }
        if (!before.equals(Files.readString(file))) throw new AssertionError("Archive changed");
        System.out.println("CONFIRMED: valid fresh API records cannot repair legacy archive through normal merge/save");
        System.out.println("Scope: safety rejection is deliberate; missing recovery path blocks current legacy installations");
    }
}
