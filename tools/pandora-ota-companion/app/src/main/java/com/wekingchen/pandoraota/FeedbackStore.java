package com.wekingchen.pandoraota;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.*;

/** Local form draft and dispatch journal; never stores PAT or sends a request on restore. */
final class FeedbackStore {
    private final SharedPreferences prefs;
    FeedbackStore(Context c) { prefs=c.getSharedPreferences("boot_feedback_v1",Context.MODE_PRIVATE); }
    JSONObject draft() { return object("draft"); }
    JSONObject submission() { return object("submission"); }
    JSONArray history() { try{return new JSONArray(prefs.getString("history","[]"));}catch(Exception e){return new JSONArray();} }
    void draft(JSONObject value) { save("draft",value); }
    void submission(JSONObject value) {
        if(value==null) { if(!prefs.edit().remove("submission").commit())throw new IllegalStateException("反馈记录保存失败");return; }
        save("submission",value);
        try {
            JSONArray old=history(), next=new JSONArray();next.put(value);
            for(int i=0;i<old.length()&&next.length()<20;i++) {
                JSONObject item=old.getJSONObject(i);
                if(!item.optString("request_id").equals(value.optString("request_id")))next.put(item);
            }
            if(!prefs.edit().putString("history",next.toString()).commit())throw new IllegalStateException("反馈历史保存失败");
        } catch(JSONException e){throw new IllegalStateException("反馈历史格式错误",e);}
    }
    private JSONObject object(String key) { try{return new JSONObject(prefs.getString(key,"{}"));}catch(Exception e){return new JSONObject();} }
    private void save(String key,JSONObject value) {
        if(!prefs.edit().putString(key,value.toString()).commit())throw new IllegalStateException("本地反馈记录保存失败，未继续操作");
    }
}
