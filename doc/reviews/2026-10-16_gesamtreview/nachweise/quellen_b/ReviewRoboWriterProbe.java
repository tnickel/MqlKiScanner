import de.robomonitor.model.SignalAccount;
import de.robomonitor.store.DataStore;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Same-JVM multi-store writer audit, solely in the review directory. */
public class ReviewRoboWriterProbe {
  public static void main(String[] args) throws Exception {
    Path root=Path.of(args[0]);Files.createDirectories(root);
    CountDownLatch ready=new CountDownLatch(8),start=new CountDownLatch(1);
    AtomicInteger failures=new AtomicInteger();
    Set<String> causes=ConcurrentHashMap.newKeySet();List<Thread> threads=new ArrayList<>();
    for(int i=0;i<8;i++) {
      final int id=i;DataStore store=new DataStore(root);
      Thread t=new Thread(()->{
        SignalAccount s=new SignalAccount("synthetic",1000+id);s.setName("Synthetic "+id);
        ready.countDown();try{start.await();}catch(InterruptedException e){throw new RuntimeException(e);}
        for(int j=0;j<40;j++)try{store.saveSignals(List.of(s));}
        catch(Exception e){failures.incrementAndGet();causes.add(e.getClass().getSimpleName());}
      });threads.add(t);t.start();
    }
    ready.await();start.countDown();for(Thread t:threads)t.join();
    System.out.println("writes=320, failures="+failures+", exceptionTypes="+causes);
    System.out.println("finalLoadedRows="+new DataStore(root).loadSignals().size());
  }
}
