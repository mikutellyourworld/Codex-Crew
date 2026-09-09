import dev.codexcrew.mobile.ConnectionAddress;

public class ConnectionAddressTest {
    public static void main(String[] args) {
        assert ConnectionAddress.parse("https://crew.example/").equals("https://crew.example/");
        assert ConnectionAddress.parse("http://127.0.0.1:6000").equals("http://localhost:6000/");
        assert ConnectionAddress.sameOrigin("http://localhost:6000/", "http://127.0.0.1:6000/chat");
        assert !ConnectionAddress.sameOrigin("http://localhost:6000/", "http://127.0.0.1:6001/");
        assert !ConnectionAddress.sameOrigin("http://localhost:6000/", "http://localhost.evil.example:6000/");
        assert ConnectionAddress.parse("HTTPS://CREW.EXAMPLE:443").equals("https://crew.example/");
        for (String bad : new String[] {
                "http://crew.example", "https://user:pass@crew.example", "javascript:alert(1)",
                "file:///etc/hosts", "https://crew.example/?token=example", "https://crew.example/#secret",
                "https://crew.example:0", "https://crew.example:65536", "https://crew.example/subpath",
                "https://crew.example\\@evil.example", "intent://host"}) {
            boolean rejected = false;
            try { ConnectionAddress.parse(bad); }
            catch (IllegalArgumentException expected) { rejected = true; }
            assert rejected : bad;
        }
        assert ConnectionAddress.sameOrigin("https://crew.example/", "https://crew.example/chat?x=1");
        assert !ConnectionAddress.sameOrigin("https://crew.example/", "https://crew.example.evil.example/");
        assert !ConnectionAddress.sameOrigin("https://crew.example/", "http://crew.example/");
        assert !ConnectionAddress.sameOrigin("https://crew.example/", "https://user@crew.example/");
        assert !ConnectionAddress.sameOrigin("https://crew.example/", "https://crew.example:444/");
        assert !ConnectionAddress.sameOrigin("https://crew.example/", null);
        assert !ConnectionAddress.sameOrigin(null, "https://crew.example/");
        assert !ConnectionAddress.sameOrigin("https://crew.example/", "about:blank");
        System.out.println("Connection address security checks passed");
    }
}
