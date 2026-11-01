package com.wekingchen.pandoraota;

import java.util.concurrent.Executor;

/** All controller methods/callbacks run on the UI scheduler; only Query runs on the worker. */
final class ForegroundIntakeTracker {
    interface Scheduler {
        void post(Runnable task, long delayMillis);
        void cancel(Runnable task);
    }
    interface Query { String run() throws Exception; }
    interface Listener { void result(String state, Exception error); }
    private final Scheduler scheduler;
    private final Executor executor;
    private long generation;
    private String key = "";
    private Runnable pending;
    private boolean active;
    private int attempts;

    ForegroundIntakeTracker(Scheduler scheduler, Executor executor) {
        this.scheduler = scheduler;
        this.executor = executor;
    }
    static boolean terminal(String state) {
        return "ACCEPTED".equals(state) || "ALREADY_CURRENT".equals(state) || "REJECTED".equals(state);
    }
    static long delay(int attempts) {
        return Math.min(60000L, 5000L << Math.min(4, Math.max(0, attempts - 1)));
    }
    void start(String identity, Query query, Listener listener) {
        if (active && key.equals(identity)) return;
        stop();
        active = true;
        key = identity;
        attempts = 0;
        schedule(generation, query, listener, 0);
    }
    void stop() {
        active = false;
        generation++;
        if (pending != null) scheduler.cancel(pending);
        pending = null;
        key = "";
    }
    private void schedule(long ticket, Query query, Listener listener, long delay) {
        pending = () -> {
            if (!active || ticket != generation) return;
            pending = null;
            executor.execute(() -> {
                String value = "PENDING";
                Exception failure = null;
                try { value = query.run(); } catch (Exception e) { failure = e; }
                final String state = value;
                final Exception error = failure;
                scheduler.post(() -> {
                    // In-flight HTTP may finish after backgrounding, selection changes, or destroy.
                    if (!active || ticket != generation) return;
                    if (error == null && terminal(state)) active = false;
                    listener.result(state, error);
                    if (active && ticket == generation)
                        schedule(ticket, query, listener, delay(++attempts));
                }, 0);
            });
        };
        scheduler.post(pending, delay);
    }
}
