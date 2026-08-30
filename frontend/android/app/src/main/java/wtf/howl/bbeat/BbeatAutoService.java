package wtf.howl.bbeat;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;
import android.support.v4.media.MediaBrowserCompat;
import android.support.v4.media.MediaDescriptionCompat;
import android.support.v4.media.MediaMetadataCompat;
import android.support.v4.media.session.MediaSessionCompat;
import android.support.v4.media.session.PlaybackStateCompat;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.media.MediaBrowserServiceCompat;
import androidx.media.app.NotificationCompat.MediaStyle;
import androidx.media.session.MediaButtonReceiver;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

public class BbeatAutoService extends MediaBrowserServiceCompat {
    private static final String TAG = "BbeatAutoService";
    private static final String ROOT_ID = "bbeat_queue";
    private static final String CHANNEL_ID = "bbeat_playback";
    private static final String STATE_PREFS = "bbeat_auto_state";
    private static final String STATE_QUEUE = "queue";
    private static final String STATE_INDEX = "index";
    private static final String STATE_CURRENT = "current";
    private static final int NOTIFICATION_ID = 2201;
    private static final long PAUSED_FOREGROUND_GRACE_MS = 10_000L;
    private static final long WAKE_LOCK_TIMEOUT_MS = 60L * 60L * 1000L;
    private static final long WAKE_LOCK_RENEW_MS = 30L * 60L * 1000L;
    private static final Object LOCK = new Object();

    static final class Entry {
        final int id;
        final String title;
        final String artist;
        final String album;
        final String artwork;
        final int queueIndex;

        Entry(int id, String title, String artist, String album, String artwork, int queueIndex) {
            this.id = id;
            this.title = title;
            this.artist = artist;
            this.album = album;
            this.artwork = artwork;
            this.queueIndex = queueIndex;
        }
    }

    private static BbeatAutoService instance;
    private static Entry current = new Entry(-1, "BBeat", "", "", "", -1);
    private static List<Entry> queue = new ArrayList<>();
    private static int currentIndex = 0;
    private static String playbackState = "none";
    private static long durationMs = 0;
    private static long positionMs = 0;
    private static float playbackRate = 1f;

    private MediaSessionCompat session;
    private NotificationManager notifications;
    private boolean inForeground;
    private PowerManager.WakeLock playbackWakeLock;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService artworkExecutor = Executors.newSingleThreadExecutor();
    private Bitmap notificationArtwork;
    private String notificationArtworkSource = "";
    private final Runnable renewPlaybackWakeLock = new Runnable() {
        @Override public void run() {
            String state;
            synchronized (LOCK) { state = playbackState; }
            if (!"playing".equals(state)) return;
            acquirePlaybackWakeLock();
            mainHandler.postDelayed(this, WAKE_LOCK_RENEW_MS);
        }
    };
    private final Runnable leaveForegroundAfterPause = () -> {
        String state;
        synchronized (LOCK) { state = playbackState; }
        if (!"paused".equals(state)) return;
        // El wake lock sí sobra con la música parada. El foreground service NO
        // se suelta: si lo soltásemos, volver a entrar desde la notificación
        // sería un arranque de foreground service en segundo plano, que Android
        // bloquea. Ver refreshNotification().
        releasePlaybackWakeLock();
    };

    static void openApp() {
        BbeatAutoService service = instance;
        if (service == null) return;
        Intent intent = new Intent(service, MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        service.startActivity(intent);
    }

    static void updateMetadata(Context context, Entry entry) {
        synchronized (LOCK) { current = entry; }
        persistState(context);
        BbeatAutoService service = instance;
        if (service != null) service.mainHandler.post(() -> {
            service.applyMetadata();
            service.refreshNotificationIfActive();
        });
    }

    static void updatePlaybackState(String state) {
        synchronized (LOCK) { playbackState = state; }
        BbeatAutoService service = instance;
        if (service != null) service.mainHandler.post(() -> service.applyPlaybackState(true));
    }

    static void updatePosition(long duration, long position, float rate) {
        synchronized (LOCK) {
            durationMs = duration;
            positionMs = position;
            playbackRate = rate;
        }
        BbeatAutoService service = instance;
        if (service != null) {
            service.mainHandler.post(() -> {
                service.applyMetadata();
                service.applyPlaybackState(false);
            });
        }
    }

    static void updateQueue(Context context, List<Entry> entries, int index) {
        synchronized (LOCK) {
            queue = new ArrayList<>(entries);
            currentIndex = Math.max(0, Math.min(index, Math.max(0, queue.size() - 1)));
        }
        persistState(context);
        BbeatAutoService service = instance;
        if (service != null) service.mainHandler.post(service::applyQueue);
    }

    private static JSONObject entryJson(Entry entry) throws JSONException {
        return new JSONObject()
            .put("id", entry.id)
            .put("title", entry.title)
            .put("artist", entry.artist)
            .put("album", entry.album)
            .put("artwork", entry.artwork)
            .put("queueIndex", entry.queueIndex);
    }

    private static Entry entryFromJson(JSONObject item) {
        return new Entry(
            item.optInt("id", -1), item.optString("title", "BBeat"),
            item.optString("artist", ""), item.optString("album", ""),
            item.optString("artwork", ""), item.optInt("queueIndex", -1)
        );
    }

    private static void persistState(Context context) {
        if (context == null) return;
        try {
            JSONArray items = new JSONArray();
            Entry selected;
            int index;
            synchronized (LOCK) {
                for (Entry entry : queue) items.put(entryJson(entry));
                index = currentIndex;
                selected = current;
            }
            context.getSharedPreferences(STATE_PREFS, Context.MODE_PRIVATE).edit()
                .putString(STATE_QUEUE, items.toString())
                .putInt(STATE_INDEX, index)
                .putString(STATE_CURRENT, entryJson(selected).toString())
                .apply();
        } catch (JSONException error) {
            Log.e(TAG, "No se pudo persistir la cola multimedia", error);
        }
    }

    private void restoreState() {
        SharedPreferences prefs = getSharedPreferences(STATE_PREFS, MODE_PRIVATE);
        try {
            JSONArray items = new JSONArray(prefs.getString(STATE_QUEUE, "[]"));
            List<Entry> restored = new ArrayList<>();
            for (int i = 0; i < items.length(); i++) restored.add(entryFromJson(items.getJSONObject(i)));
            synchronized (LOCK) {
                if (queue.isEmpty()) queue = restored;
                currentIndex = Math.max(0, Math.min(
                    prefs.getInt(STATE_INDEX, 0), Math.max(0, queue.size() - 1)
                ));
                if (!queue.isEmpty()) current = queue.get(currentIndex);
                else {
                    String saved = prefs.getString(STATE_CURRENT, null);
                    if (saved != null) current = entryFromJson(new JSONObject(saved));
                }
                // Nunca reanudar automáticamente al conectar el coche.
                playbackState = "paused";
            }
        } catch (JSONException error) {
            Log.e(TAG, "No se pudo restaurar la cola multimedia", error);
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        notifications = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (powerManager != null) {
            playbackWakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                getPackageName() + ":playback"
            );
            playbackWakeLock.setReferenceCounted(false);
        }
        createNotificationChannel();
        restoreState();

        session = new MediaSessionCompat(this, "BbeatAuto");
        session.setFlags(
            MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS |
            MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS |
            MediaSessionCompat.FLAG_HANDLES_QUEUE_COMMANDS
        );
        session.setCallback(new MediaSessionCompat.Callback() {
            // OJO: aquí NO se pide foco de audio, y es a propósito.
            //
            // Quien reproduce es el <audio> del WebView, y ese elemento pide su
            // propio foco al arrancar. Si el servicio lo pide también, el
            // WebView se lo quita medio segundo después, nos llega
            // AUDIOFOCUS_LOSS, y un listener que reaccione pausando corta la
            // canción al instante: sonaba un milisegundo y se paraba.
            // Dos componentes de la misma app no pueden competir por el foco.
            @Override public void onPlay() {
                // Reclamar el foreground AQUÍ y no al volver del WebView. Entre
                // el botón de la notificación y el evento 'play' del <audio>
                // hay un viaje entero a JavaScript, y para entonces Android ya
                // ha cerrado el permiso temporal que concede al entregar el
                // botón multimedia: startForeground falla y la app se queda sin
                // notificación y sin protección.
                enterForeground("playing");
                BbeatAutoPlugin.dispatchAction("play", null, null);
            }
            @Override public void onPause() { BbeatAutoPlugin.dispatchAction("pause", null, null); }
            @Override public void onStop() { BbeatAutoPlugin.dispatchAction("stop", null, null); }
            @Override public void onSkipToNext() { BbeatAutoPlugin.dispatchAction("nexttrack", null, null); }
            @Override public void onSkipToPrevious() { BbeatAutoPlugin.dispatchAction("previoustrack", null, null); }
            @Override public void onSeekTo(long pos) { BbeatAutoPlugin.dispatchAction("seekto", pos, null); }
            @Override public void onSkipToQueueItem(long id) {
                BbeatAutoPlugin.dispatchAction("playfrommediaid", null, (int) id);
            }
            @Override public void onPlayFromMediaId(String mediaId, Bundle extras) {
                try {
                    int index = Integer.parseInt(mediaId.substring(mediaId.lastIndexOf(':') + 1));
                    BbeatAutoPlugin.dispatchAction("playfrommediaid", null, index);
                } catch (RuntimeException ignored) {
                }
            }
            @Override public void onPlayFromSearch(String queryText, Bundle extras) {
                String queryTextNormalized = queryText == null ? "" : queryText.trim().toLowerCase(Locale.ROOT);
                List<Entry> snapshot;
                int selected;
                synchronized (LOCK) {
                    snapshot = new ArrayList<>(queue);
                    selected = currentIndex;
                }
                if (!queryTextNormalized.isEmpty()) {
                    for (int i = 0; i < snapshot.size(); i++) {
                        Entry item = snapshot.get(i);
                        String searchable = (item.title + " " + item.artist + " " + item.album)
                            .toLowerCase(Locale.ROOT);
                        if (searchable.contains(queryTextNormalized)) {
                            selected = i;
                            break;
                        }
                    }
                }
                if (!snapshot.isEmpty()) {
                    BbeatAutoPlugin.dispatchAction(
                        "playfrommediaid", null, snapshot.get(selected).queueIndex
                    );
                }
                else BbeatAutoPlugin.dispatchAction("play", null, null);
            }
        });
        session.setSessionActivity(PendingIntent.getActivity(
            this,
            0,
            new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        ));
        session.setActive(true);
        setSessionToken(session.getSessionToken());
        applyMetadata();
        applyQueue();
        applyPlaybackState(false);
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // El audio lo reproduce el <audio> del WebView, que vive dentro de la
        // Activity: si el usuario desliza la app fuera de recientes, la música
        // se para se haga lo que se haga aquí. Lo único que podemos evitar es
        // dejar una notificación zombi diciendo que suena algo.
        synchronized (LOCK) { playbackState = "none"; }
        stopKeepingPlaybackAwake();
        try {
            stopForeground(STOP_FOREGROUND_REMOVE);
            notifications.cancel(NOTIFICATION_ID);
        } catch (RuntimeException error) {
            Log.e(TAG, "Limpieza tras cerrar la app", error);
        }
        inForeground = false;
        super.onTaskRemoved(rootIntent);
        stopSelf();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // START_STICKY puede reabrir el servicio con intent == null.
        if (intent != null) {
            try {
                MediaButtonReceiver.handleIntent(session, intent);
            } catch (RuntimeException error) {
                Log.e(TAG, "No se pudo procesar el intent multimedia", error);
            }
        }
        return START_STICKY;
    }

    @Nullable
    @Override
    public BrowserRoot onGetRoot(@NonNull String clientPackageName, int clientUid, @Nullable Bundle rootHints) {
        return new BrowserRoot(ROOT_ID, null);
    }

    @Override
    public void onLoadChildren(@NonNull String parentId, @NonNull Result<List<MediaBrowserCompat.MediaItem>> result) {
        if (!ROOT_ID.equals(parentId)) {
            result.sendResult(Collections.emptyList());
            return;
        }
        List<Entry> snapshot;
        synchronized (LOCK) { snapshot = new ArrayList<>(queue); }
        List<MediaBrowserCompat.MediaItem> items = new ArrayList<>();
        for (Entry item : snapshot) items.add(browserItem(item));
        result.sendResult(items);
    }

    @Override
    public void onSearch(
        @NonNull String queryText,
        Bundle extras,
        @NonNull Result<List<MediaBrowserCompat.MediaItem>> result
    ) {
        String query = queryText.trim().toLowerCase(Locale.ROOT);
        List<Entry> snapshot;
        synchronized (LOCK) { snapshot = new ArrayList<>(queue); }
        List<MediaBrowserCompat.MediaItem> matches = new ArrayList<>();
        for (Entry item : snapshot) {
            String searchable = (item.title + " " + item.artist + " " + item.album)
                .toLowerCase(Locale.ROOT);
            if (query.isEmpty() || searchable.contains(query)) matches.add(browserItem(item));
        }
        result.sendResult(matches);
    }

    private MediaBrowserCompat.MediaItem browserItem(Entry item) {
        MediaDescriptionCompat.Builder description = new MediaDescriptionCompat.Builder()
            .setMediaId("queue:" + item.queueIndex)
            .setTitle(item.title)
            .setSubtitle(item.artist)
            .setDescription(item.album);
        Uri artworkUri = BbeatArtworkProvider.uriFor(this, item.artwork);
        if (artworkUri != null) description.setIconUri(artworkUri);
        return new MediaBrowserCompat.MediaItem(
            description.build(), MediaBrowserCompat.MediaItem.FLAG_PLAYABLE
        );
    }

    private void applyMetadata() {
        if (session == null) return;
        Entry entry;
        long duration;
        synchronized (LOCK) { entry = current; duration = durationMs; }
        MediaMetadataCompat.Builder builder = new MediaMetadataCompat.Builder()
            .putString(MediaMetadataCompat.METADATA_KEY_MEDIA_ID, String.valueOf(entry.id))
            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, entry.title)
            .putString(MediaMetadataCompat.METADATA_KEY_DISPLAY_TITLE, entry.title)
            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, entry.artist)
            .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, entry.album)
            .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, duration);
        Uri artworkUri = BbeatArtworkProvider.uriFor(this, entry.artwork);
        if (artworkUri != null) {
            String localArtwork = artworkUri.toString();
            builder.putString(MediaMetadataCompat.METADATA_KEY_ALBUM_ART_URI, localArtwork);
            builder.putString(MediaMetadataCompat.METADATA_KEY_ART_URI, localArtwork);
            builder.putString(MediaMetadataCompat.METADATA_KEY_DISPLAY_ICON_URI, localArtwork);
        }
        try {
            session.setMetadata(builder.build());
        } catch (RuntimeException error) {
            Log.e(TAG, "No se pudo actualizar la metadata", error);
        }
        requestNotificationArtwork(entry.artwork);
    }

    private void applyQueue() {
        if (session == null) return;
        List<Entry> snapshot;
        int selected;
        synchronized (LOCK) { snapshot = new ArrayList<>(queue); selected = currentIndex; }
        List<MediaSessionCompat.QueueItem> nativeQueue = new ArrayList<>();
        for (int i = 0; i < snapshot.size(); i++) {
            Entry item = snapshot.get(i);
            MediaDescriptionCompat.Builder description = new MediaDescriptionCompat.Builder()
                .setMediaId("queue:" + item.queueIndex)
                .setTitle(item.title)
                .setSubtitle(item.artist)
                .setDescription(item.album);
            Uri artworkUri = BbeatArtworkProvider.uriFor(this, item.artwork);
            if (artworkUri != null) description.setIconUri(artworkUri);
            nativeQueue.add(new MediaSessionCompat.QueueItem(description.build(), item.queueIndex));
        }
        try {
            session.setQueue(nativeQueue);
            session.setQueueTitle("Cola de BBeat");
        } catch (RuntimeException error) {
            Log.e(TAG, "No se pudo actualizar la cola de Android Auto", error);
        }
        if (!snapshot.isEmpty() && selected < snapshot.size()) {
            synchronized (LOCK) { current = snapshot.get(selected); }
            applyMetadata();
            applyPlaybackState(false);
        }
        notifyChildrenChanged(ROOT_ID);
    }

    private void applyPlaybackState(boolean refreshNotification) {
        if (session == null) return;
        String state;
        long position;
        float rate;
        long activeQueueItemId;
        synchronized (LOCK) {
            state = playbackState;
            position = positionMs;
            rate = playbackRate;
            activeQueueItemId = current.queueIndex;
        }
        int nativeState = "playing".equals(state)
            ? PlaybackStateCompat.STATE_PLAYING
            : "paused".equals(state) ? PlaybackStateCompat.STATE_PAUSED : PlaybackStateCompat.STATE_STOPPED;
        long actions = PlaybackStateCompat.ACTION_PLAY | PlaybackStateCompat.ACTION_PAUSE |
            PlaybackStateCompat.ACTION_PLAY_PAUSE | PlaybackStateCompat.ACTION_SKIP_TO_NEXT |
            PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS | PlaybackStateCompat.ACTION_SEEK_TO |
            PlaybackStateCompat.ACTION_PLAY_FROM_MEDIA_ID | PlaybackStateCompat.ACTION_PLAY_FROM_SEARCH |
            PlaybackStateCompat.ACTION_SKIP_TO_QUEUE_ITEM | PlaybackStateCompat.ACTION_STOP;
        try {
            session.setPlaybackState(new PlaybackStateCompat.Builder()
                .setActions(actions)
                .setActiveQueueItemId(activeQueueItemId)
                .setState(nativeState, position, rate)
                .build());
            if (refreshNotification) refreshNotification(state);
        } catch (RuntimeException error) {
            Log.e(TAG, "No se pudo actualizar el estado multimedia", error);
        }
    }

    private void refreshNotificationIfActive() {
        String state;
        synchronized (LOCK) { state = playbackState; }
        if (!"none".equals(state)) refreshNotification(state);
    }

    private void requestNotificationArtwork(String remoteUrl) {
        String source = remoteUrl == null ? "" : remoteUrl;
        if (source.equals(notificationArtworkSource)) return;
        notificationArtworkSource = source;
        notificationArtwork = null;
        if (source.isEmpty()) {
            refreshNotificationIfActive();
            return;
        }
        Uri localUri = BbeatArtworkProvider.uriFor(this, source);
        if (localUri == null) return;
        artworkExecutor.execute(() -> {
            Bitmap decoded = null;
            try (java.io.InputStream input = getContentResolver().openInputStream(localUri)) {
                decoded = BitmapFactory.decodeStream(input);
                if (decoded != null && (decoded.getWidth() > 512 || decoded.getHeight() > 512)) {
                    float ratio = Math.min(512f / decoded.getWidth(), 512f / decoded.getHeight());
                    decoded = Bitmap.createScaledBitmap(
                        decoded,
                        Math.max(1, Math.round(decoded.getWidth() * ratio)),
                        Math.max(1, Math.round(decoded.getHeight() * ratio)),
                        true
                    );
                }
            } catch (Exception error) {
                Log.w(TAG, "No se pudo cargar la carátula de la notificación", error);
            }
            Bitmap ready = decoded;
            mainHandler.post(() -> {
                if (source.equals(notificationArtworkSource)) {
                    notificationArtwork = ready;
                    refreshNotificationIfActive();
                }
            });
        });
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "Reproducción", NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Controles de reproducción de BBeat");
            notifications.createNotificationChannel(channel);
        }
    }

    private PendingIntent mediaButton(long action) {
        return MediaButtonReceiver.buildMediaButtonPendingIntent(this, action);
    }

    private Notification buildNotification(String state) {
        Entry entry;
        synchronized (LOCK) { entry = current; }
        boolean playing = "playing".equals(state);
        PendingIntent contentIntent = PendingIntent.getActivity(
            this,
            0,
            new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_bbeat)
            .setContentTitle(entry.title.isEmpty() ? "BBeat" : entry.title)
            .setContentText(entry.artist)
            .setContentIntent(contentIntent)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setOngoing(playing)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(R.drawable.ic_media_previous, "Anterior", mediaButton(PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS))
            .addAction(
                playing ? R.drawable.ic_media_pause : R.drawable.ic_media_play,
                playing ? "Pausar" : "Reproducir",
                mediaButton(playing ? PlaybackStateCompat.ACTION_PAUSE : PlaybackStateCompat.ACTION_PLAY)
            )
            .addAction(R.drawable.ic_media_next, "Siguiente", mediaButton(PlaybackStateCompat.ACTION_SKIP_TO_NEXT))
            .setStyle(new MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1, 2));
        if (notificationArtwork != null) builder.setLargeIcon(notificationArtwork);
        return builder.build();
    }

    private void refreshNotification(String state) {
        mainHandler.removeCallbacks(leaveForegroundAfterPause);
        if ("none".equals(state)) {
            stopKeepingPlaybackAwake();
                stopForeground(STOP_FOREGROUND_REMOVE);
            inForeground = false;
            notifications.cancel(NOTIFICATION_ID);
            return;
        }
        if ("playing".equals(state)) {
            keepPlaybackAwake();
            enterForeground(state);
            return;
        }
        // Pausa: se suelta el wake lock tras la gracia, pero el servicio SIGUE
        // en foreground. Si lo soltásemos, volver a entrar desde la
        // notificación sería un arranque de foreground service en segundo
        // plano, que Android bloquea — y era justo lo que dejaba la app sin
        // notificación y sin protección, con la música cortándose al minimizar.
        mainHandler.removeCallbacks(renewPlaybackWakeLock);
        mainHandler.postDelayed(leaveForegroundAfterPause, PAUSED_FOREGROUND_GRACE_MS);
        // Si aún no somos foreground (p. ej. la primera acción fue una pausa),
        // entramos ahora; si ya lo somos, startForeground solo refresca.
        enterForeground(state);
    }

    /**
     * Entra (o se mantiene) en foreground mostrando la notificación.
     *
     * Es el único punto donde se llama a startForeground, para que la
     * transición no dependa de por dónde llegó el cambio de estado. Si Android
     * lo rechaza —arranque de foreground service desde segundo plano— al menos
     * la notificación se publica igual, y queda en el log qué pasó en vez de
     * desaparecer todo en silencio.
     */
    private void enterForeground(String state) {
        Notification notification = buildNotification(state);
        try {
            startForeground(NOTIFICATION_ID, notification);
            if (!inForeground) Log.i(TAG, "foreground service activo (" + state + ")");
            inForeground = true;
        } catch (RuntimeException error) {
            inForeground = false;
            Log.e(TAG, "Android rechazó el foreground service (" +
                error.getClass().getSimpleName() + "): la reproducción en segundo " +
                "plano queda desprotegida", error);
            try {
                notifications.notify(NOTIFICATION_ID, notification);
            } catch (RuntimeException notifyError) {
                Log.e(TAG, "Tampoco se pudo publicar la notificación", notifyError);
            }
        }
    }

    private void keepPlaybackAwake() {
        mainHandler.removeCallbacks(renewPlaybackWakeLock);
        renewPlaybackWakeLock.run();
    }

    private void acquirePlaybackWakeLock() {
        if (playbackWakeLock == null) return;
        try {
            // El timeout protege ante un proceso atascado; se renueva mientras
            // MediaSession continúe en playing y en cada cambio de pista.
            if (playbackWakeLock.isHeld()) playbackWakeLock.release();
            playbackWakeLock.acquire(WAKE_LOCK_TIMEOUT_MS);
        } catch (RuntimeException error) {
            Log.e(TAG, "No se pudo mantener despierta la transición de audio", error);
        }
    }

    private void releasePlaybackWakeLock() {
        if (playbackWakeLock == null) return;
        try {
            if (playbackWakeLock.isHeld()) playbackWakeLock.release();
        } catch (RuntimeException error) {
            Log.e(TAG, "No se pudo liberar el wake lock de reproducción", error);
        }
    }

    private void stopKeepingPlaybackAwake() {
        mainHandler.removeCallbacks(renewPlaybackWakeLock);
        releasePlaybackWakeLock();
    }

    @Override
    public void onDestroy() {
        if (instance == this) instance = null;
        mainHandler.removeCallbacks(leaveForegroundAfterPause);
        stopKeepingPlaybackAwake();
        if (session != null) {
            session.setActive(false);
            session.release();
        }
        artworkExecutor.shutdownNow();
        super.onDestroy();
    }
}
