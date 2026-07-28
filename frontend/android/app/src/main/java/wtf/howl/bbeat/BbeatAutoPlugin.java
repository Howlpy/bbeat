package wtf.howl.bbeat;

import android.content.Intent;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONException;
import org.json.JSONArray;
import org.json.JSONObject;

@CapacitorPlugin(name = "BbeatAuto")
public class BbeatAutoPlugin extends Plugin {
    private static BbeatAutoPlugin activePlugin;
    private static JSObject pendingAction;

    @Override
    public void load() {
        activePlugin = this;
        getContext().startService(new Intent(getContext(), BbeatAutoService.class));
        if (pendingAction != null) {
            notifyListeners("action", pendingAction, true);
            pendingAction = null;
        }
    }

    @Override
    protected void handleOnDestroy() {
        if (activePlugin == this) activePlugin = null;
        super.handleOnDestroy();
    }

    static void dispatchAction(String action, Long seekTimeMs, Integer index) {
        JSObject data = new JSObject();
        data.put("action", action);
        if (seekTimeMs != null) data.put("seekTime", seekTimeMs / 1000.0);
        if (index != null) data.put("index", index);
        if (activePlugin != null) {
            activePlugin.notifyListeners("action", data, true);
            return;
        }
        pendingAction = data;
        BbeatAutoService.openApp();
    }

    private static String artworkFrom(JSONObject item) {
        try {
            Object raw = item.opt("artwork");
            JSONArray artwork = raw instanceof JSONArray
                ? (JSONArray) raw
                : new JSONArray(raw instanceof String ? (String) raw : "[]");
            if (artwork.length() > 0) {
                return artwork.getJSONObject(0).optString("src", "");
            }
        } catch (JSONException ignored) {
        }
        return "";
    }

    @PluginMethod
    public void setMetadata(PluginCall call) {
        BbeatAutoService.updateMetadata(getContext(), new BbeatAutoService.Entry(
            -1,
            call.getString("title", ""),
            call.getString("artist", ""),
            call.getString("album", ""),
            artworkFrom(call.getData()),
            -1
        ));
        call.resolve();
    }

    @PluginMethod
    public void setPlaybackState(PluginCall call) {
        BbeatAutoService.updatePlaybackState(call.getString("playbackState", "none"));
        call.resolve();
    }

    @PluginMethod
    public void setPositionState(PluginCall call) {
        double duration = call.getDouble("duration", 0.0);
        double position = call.getDouble("position", 0.0);
        double rate = call.getDouble("playbackRate", 1.0);
        BbeatAutoService.updatePosition(
            Math.round(duration * 1000),
            Math.round(position * 1000),
            (float) rate
        );
        call.resolve();
    }

    @PluginMethod
    public void setQueue(PluginCall call) {
        List<BbeatAutoService.Entry> entries = new ArrayList<>();
        JSArray items = call.getArray("items", new JSArray());
        if (items == null) items = new JSArray();
        for (int i = 0; i < items.length(); i++) {
            try {
                JSONObject item = items.getJSONObject(i);
                entries.add(new BbeatAutoService.Entry(
                    item.optInt("id", i),
                    item.optString("title", ""),
                    item.optString("artist", ""),
                    item.optString("album", ""),
                    artworkFrom(item),
                    item.optInt("queueIndex", i)
                ));
            } catch (JSONException ignored) {
            }
        }
        BbeatAutoService.updateQueue(getContext(), entries, call.getInt("currentIndex", 0));
        call.resolve();
    }
}
