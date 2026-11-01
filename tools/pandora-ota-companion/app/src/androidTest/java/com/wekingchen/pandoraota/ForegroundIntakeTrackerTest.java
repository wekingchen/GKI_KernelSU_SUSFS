package com.wekingchen.pandoraota;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.*;
import java.io.IOException;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class ForegroundIntakeTrackerTest {
    static class Scheduler implements ForegroundIntakeTracker.Scheduler {
        final List<Runnable> tasks = new ArrayList<>();
        long lastDelay;
        public void post(Runnable r, long delay) { tasks.add(r); lastDelay = delay; }
        public void cancel(Runnable r) { tasks.remove(r); }
        void next() { assertFalse(tasks.isEmpty()); tasks.remove(0).run(); }
    }
    @Test public void pendingTransitionsToEveryTerminalAndStops() {
        for (String terminal : Arrays.asList("ACCEPTED", "ALREADY_CURRENT", "REJECTED")) {
            Scheduler s = new Scheduler();
            ForegroundIntakeTracker t = new ForegroundIntakeTracker(s, Runnable::run);
            List<String> result = new ArrayList<>(); int[] queryCount = {0};
            t.start("receipt-a", () -> ++queryCount[0] == 1 ? "PENDING" : terminal,
                    (state, error) -> { assertNull(error); result.add(state); });
            s.next(); s.next(); // query + UI result
            assertEquals(5000, s.lastDelay);
            s.next(); s.next();
            assertEquals(Arrays.asList("PENDING", terminal), result);
            assertTrue(s.tasks.isEmpty());
        }
    }
    @Test public void backgroundingDiscardsInflightResultAndResumeFetchesAgain() {
        Scheduler s = new Scheduler(); List<Runnable> work = new ArrayList<>();
        ForegroundIntakeTracker t = new ForegroundIntakeTracker(s, work::add);
        List<String> result = new ArrayList<>();
        t.start("receipt-a", () -> "ACCEPTED", (state, error) -> result.add(state));
        s.next(); t.stop(); work.remove(0).run(); s.next();
        assertTrue(result.isEmpty()); assertTrue(s.tasks.isEmpty());
        t.start("receipt-a", () -> "ALREADY_CURRENT", (state, error) -> result.add(state));
        s.next(); work.remove(0).run(); s.next();
        assertEquals(Collections.singletonList("ALREADY_CURRENT"), result);
    }
    @Test public void changingArchiveCannotApplyOldReceiptToNewSelection() {
        Scheduler s = new Scheduler(); List<Runnable> work = new ArrayList<>();
        ForegroundIntakeTracker t = new ForegroundIntakeTracker(s, work::add);
        List<String> result = new ArrayList<>();
        t.start("old", () -> "ACCEPTED", (state, error) -> result.add("old")); s.next();
        t.start("new", () -> "REJECTED", (state, error) -> result.add("new"));
        work.remove(0).run(); s.next(); // starts new
        s.next(); // old response discarded
        work.remove(0).run(); s.next();
        assertEquals(Collections.singletonList("new"), result);
    }
    @Test public void transientFailurePreservesPendingAndRetriesWithoutUpload() {
        Scheduler s = new Scheduler(); ForegroundIntakeTracker t = new ForegroundIntakeTracker(s, Runnable::run);
        List<String> result = new ArrayList<>(); int[] count = {0};
        t.start("receipt", () -> { if (++count[0] == 1) throw new IOException("offline"); return "ACCEPTED"; },
                (state, error) -> result.add(error == null ? state : "retry"));
        s.next(); s.next(); s.next(); s.next();
        assertEquals(Arrays.asList("retry", "ACCEPTED"), result);
        assertTrue(s.tasks.isEmpty());
        assertEquals(60000, ForegroundIntakeTracker.delay(100));
    }
    @Test public void refreshDoesNotQueueDuplicatePollsAndStopCancelsScheduledRequest() {
        Scheduler s = new Scheduler(); ForegroundIntakeTracker t = new ForegroundIntakeTracker(s, Runnable::run);
        for (int i = 0; i < 20; i++) t.start("same", () -> "PENDING", (state, error) -> {});
        assertEquals(1, s.tasks.size());
        t.stop(); assertTrue(s.tasks.isEmpty());
    }
}
