package com.wekingchen.pandoraota;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Backend receipt parsing never treats upload/dispatch alone as accepted OTA input. */
@RunWith(AndroidJUnit4.class)
public class IntakeReceiptEmulatorTest {
    private static final String SHA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    private JSONObject draft(String body) throws Exception {
        JSONObject release = new JSONObject();
        release.put("draft", true);
        release.put("tag_name", "pandora-ota-capture-1730000000000");
        release.put("body", body);
        return release;
    }

    @Test
    public void noServerReportIsPending() throws Exception {
        assertEquals("PENDING", GitHubUploader.parseIntakeReceipt(
                draft("Unverified read-only mobile snapshot"), 567, SHA));
    }

    @Test
    public void acceptedServerReportRequiresMatchingAssetAndHash() throws Exception {
        String body = "MOBILE_OTA_INTAKE=ACCEPTED\n"
                + "MOBILE_ASSET_ID=567\nMOBILE_SOURCE_SHA256=" + SHA + "\n";
        assertEquals("ACCEPTED", GitHubUploader.parseIntakeReceipt(draft(body), 567, SHA));
        try {
            GitHubUploader.parseIntakeReceipt(draft(body), 568, SHA);
            fail("mismatched asset cannot be accepted");
        } catch (SecurityException expected) { }
        try {
            GitHubUploader.parseIntakeReceipt(draft(body), 567,
                    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");
            fail("mismatched source SHA cannot be accepted");
        } catch (SecurityException expected) { }
    }

    @Test
    public void rejectedIsNotSilentlyTreatedAsSuccessful() throws Exception {
        String body = "MOBILE_OTA_INTAKE=REJECTED\n"
                + "MOBILE_ASSET_ID=567\nMOBILE_SOURCE_SHA256=" + SHA + "\n";
        assertEquals("REJECTED", GitHubUploader.parseIntakeReceipt(draft(body), 567, SHA));
    }

    @Test
    public void neverTrustNonDraftAsIntakeReceipt() throws Exception {
        JSONObject release = draft("MOBILE_OTA_INTAKE=ACCEPTED\n"
                + "MOBILE_ASSET_ID=567\nMOBILE_SOURCE_SHA256=" + SHA + "\n");
        release.put("draft", false);
        try {
            GitHubUploader.parseIntakeReceipt(release, 567, SHA);
            fail("non-draft must not be trusted");
        } catch (SecurityException expected) { }
    }
}
