package wtf.howl.bbeat;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
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

public class BbeatAutoService extends MediaBrowserServiceCompat {
    private static final String ROOT_ID = "bbeat_queue";
    private static final String CHANNEL_ID = "bbeat_playback";
    private static final int NOTIFICATION_ID = 2201;
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

    static void openApp() {
        BbeatAutoService service = instance;
        if (service == null) return;
        Intent intent = new Intent(service, MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        service.startActivity(intent);
    }

    static void updateMetadata(Entry entry) {
        synchronized (LOCK) { current = entry; }
        if (instance != null) instance.applyMetadata();
    }

    static void updatePlaybackState(String state) {
        synchronized (LOCK) { playbackState = state; }
        if (instance != null) instance.applyPlaybackState(true);
    }

    static void updatePosition(long duration, long position, float rate) {
        synchronized (LOCK) {
            durationMs = duration;
            positionMs = position;
            playbackRate = rate;
        }
        if (instance != null) {
            instance.applyMetadata();
            instance.applyPlaybackState(false);
        }
    }

    static void updateQueue(List<Entry> entries, int index) {
        synchronized (LOCK) {
            queue = new ArrayList<>(entries);
            currentIndex = Math.max(0, Math.min(index, Math.max(0, queue.size() - 1)));
        }
        if (instance != null) instance.applyQueue();
    }

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        notifications = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        createNotificationChannel();

        session = new MediaSessionCompat(this, "BbeatAuto");
        session.setFlags(
            MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS |
            MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS |
            MediaSessionCompat.FLAG_HANDLES_QUEUE_COMMANDS
        );
        session.setCallback(new MediaSessionCompat.Callback() {
            @Override public void onPlay() { BbeatAutoPlugin.dispatchAction("play", null, null); }
            @Override public void onPause() { BbeatAutoPlugin.dispatchAction("pause", null, null); }
            @Override public void onStop() { BbeatAutoPlugin.dispatchAction("stop", null, null); }
            @Override public void onSkipToNext() { BbeatAutoPlugin.dispatchAction("nexttrack", null, null); }
            @Override public void onSkipToPrevious() { BbeatAutoPlugin.dispatchAction("previoustrack", null, null); }
            @Override public void onSeekTo(long pos) { BbeatAutoPlugin.dispatchAction("seekto", pos, null); }
            @Override public void onPlayFromMediaId(String mediaId, Bundle extras) {
                try {
                    int index = Integer.parseInt(mediaId.substring(mediaId.lastIndexOf(':') + 1));
                    BbeatAutoPlugin.dispatchAction("playfrommediaid", null, index);
                } catch (RuntimeException ignored) {
                }
            }
            @Override public void onPlayFromSearch(String queryText, Bundle extras) {
                String queryTextNormalized = queryText == null ? "" : queryText.trim().toLowerCase();
                List<Entry> snapshot;
                int selected;
                synchronized (LOCK) {
                    snapshot = new ArrayList<>(queue);
                    selected = currentIndex;
                }
                if (!queryTextNormalized.isEmpty()) {
                    for (int i = 0; i < snapshot.size(); i++) {
                        Entry item = snapshot.get(i);
                        String searchable = (item.title + " " + item.artist + " " + item.album).toLowerCase();
                        if (searchable.contains(queryTextNormalized)) {
                            selected = i;
                            break;
                        }
                    }
                }
                if (!snapshot.isEmpty()) BbeatAutoPlugin.dispatchAction("playfrommediaid", null, selected);
                else BbeatAutoPlugin.dispatchAction("play", null, null);
            }
        });
        session.setActive(true);
        setSessionToken(session.getSessionToken());
        applyMetadata();
        applyQueue();
        applyPlaybackState(false);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        MediaButtonReceiver.handleIntent(session, intent);
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
        for (int i = 0; i < snapshot.size(); i++) {
            Entry item = snapshot.get(i);
            MediaDescriptionCompat.Builder description = new MediaDescriptionCompat.Builder()
                .setMediaId("queue:" + item.queueIndex)
                .setTitle(item.title)
                .setSubtitle(item.artist)
                .setDescription(item.album);
            if (!item.artwork.isEmpty()) description.setIconUri(Uri.parse(item.artwork));
            items.add(new MediaBrowserCompat.MediaItem(description.build(), MediaBrowserCompat.MediaItem.FLAG_PLAYABLE));
        }
        result.sendResult(items);
    }

    private void applyMetadata() {
        if (session == null) return;
        Entry entry;
        long duration;
        synchronized (LOCK) { entry = current; duration = durationMs; }
        MediaMetadataCompat.Builder builder = new MediaMetadataCompat.Builder()
            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, entry.title)
            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, entry.artist)
            .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, entry.album)
            .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, duration);
        if (!entry.artwork.isEmpty()) {
            builder.putString(MediaMetadataCompat.METADATA_KEY_ALBUM_ART_URI, entry.artwork);
            builder.putString(MediaMetadataCompat.METADATA_KEY_DISPLAY_ICON_URI, entry.artwork);
        }
        session.setMetadata(builder.build());
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
            if (!item.artwork.isEmpty()) description.setIconUri(Uri.parse(item.artwork));
            nativeQueue.add(new MediaSessionCompat.QueueItem(description.build(), item.queueIndex));
        }
        session.setQueue(nativeQueue);
        session.setQueueTitle("Cola de BBeat");
        if (!snapshot.isEmpty() && selected < snapshot.size()) current = snapshot.get(selected);
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
            : "paused".equals(state) ? PlaybackStateCompat.STATE_PAUSED : PlaybackStateCompat.STATE_NONE;
        long actions = PlaybackStateCompat.ACTION_PLAY | PlaybackStateCompat.ACTION_PAUSE |
            PlaybackStateCompat.ACTION_PLAY_PAUSE | PlaybackStateCompat.ACTION_SKIP_TO_NEXT |
            PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS | PlaybackStateCompat.ACTION_SEEK_TO |
            PlaybackStateCompat.ACTION_PLAY_FROM_MEDIA_ID | PlaybackStateCompat.ACTION_STOP;
        session.setPlaybackState(new PlaybackStateCompat.Builder()
            .setActions(actions)
            .setActiveQueueItemId(activeQueueItemId)
            .setState(nativeState, position, rate)
            .build());
        if (refreshNotification) refreshNotification(state);
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
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_bbeat)
            .setContentTitle(entry.title.isEmpty() ? "BBeat" : entry.title)
            .setContentText(entry.artist)
            .setContentIntent(contentIntent)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(R.drawable.ic_stat_bbeat, "Anterior", mediaButton(PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS))
            .addAction(
                R.drawable.ic_stat_bbeat,
                playing ? "Pausar" : "Reproducir",
                mediaButton(playing ? PlaybackStateCompat.ACTION_PAUSE : PlaybackStateCompat.ACTION_PLAY)
            )
            .addAction(R.drawable.ic_stat_bbeat, "Siguiente", mediaButton(PlaybackStateCompat.ACTION_SKIP_TO_NEXT))
            .setStyle(new MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1, 2))
            .build();
    }

    private void refreshNotification(String state) {
        if ("none".equals(state)) {
            stopForeground(STOP_FOREGROUND_REMOVE);
            notifications.cancel(NOTIFICATION_ID);
            return;
        }
        Notification notification = buildNotification(state);
        if ("playing".equals(state)) startForeground(NOTIFICATION_ID, notification);
        else {
            stopForeground(STOP_FOREGROUND_DETACH);
            notifications.notify(NOTIFICATION_ID, notification);
        }
    }

    @Override
    public void onDestroy() {
        if (instance == this) instance = null;
        if (session != null) {
            session.setActive(false);
            session.release();
        }
        super.onDestroy();
    }
}
