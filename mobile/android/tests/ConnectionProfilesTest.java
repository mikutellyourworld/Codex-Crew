import dev.codexcrew.mobile.ConnectionProfiles;

public class ConnectionProfilesTest {
    public static void main(String[] args) {
        assert ConnectionProfiles.validate(false, "http://127.0.0.1:5486/").equals("http://localhost:5486/");
        assert ConnectionProfiles.validate(true, "https://example.com:443/").equals("https://example.com/");
        reject(true, "http://localhost:5486/");
        reject(false, "https://example.com/");
        reject(false, "http://example.com/");
        reject(true, "https://user:secret@example.com/");
        reject(true, "https://example.com/?token=secret");
        reject(true, "");
        reject(true, null);
        assert ConnectionProfiles.fallback("http://localhost:5486/", "https://example.com/").equals("https://example.com/");
        assert ConnectionProfiles.fallback("https://example.com/", "https://backup.example.com/") == null;
        assert ConnectionProfiles.fallback("http://localhost:5486/", "http://localhost:5487/") == null;
        assert ConnectionProfiles.fallback("http://localhost:5486/", "") == null;
        assert ConnectionProfiles.fallback(null, "https://example.com/") == null;
        ConnectionProfiles.Health health = new ConnectionProfiles.Health();
        assert !health.record(false);
        assert !health.record(true); // A successful check clears the transient failure.
        assert !health.record(false);
        assert health.record(false);
        assert !health.record(true);
        System.out.println("Connection profile and failover policy tests passed");
    }
    private static void reject(boolean https, String value) {
        try {
            ConnectionProfiles.validate(https, value);
            throw new AssertionError("Accepted invalid slot address");
        } catch (IllegalArgumentException expected) { }
    }
}
