package dev.codexcrew.mobile;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** A persisted connection is an origin, never a login URL or credential. */
public final class ConnectionAddress {
    private ConnectionAddress() {}

    public static String parse(String value) {
        try {
            URI uri = new URI(value.trim());
            String scheme = uri.getScheme();
            String host = uri.getHost();
            if (scheme == null || host == null || uri.getRawUserInfo() != null
                    || uri.getRawQuery() != null || uri.getRawFragment() != null
                    || uri.getPort() == 0 || uri.getPort() > 65535
                    || !(uri.getRawPath().isEmpty() || uri.getRawPath().equals("/"))) {
                throw new IllegalArgumentException();
            }
            scheme = scheme.toLowerCase(Locale.ROOT);
            host = host.toLowerCase(Locale.ROOT);
            if (!scheme.equals("https") && !(scheme.equals("http")
                    && (host.equals("127.0.0.1") || host.equals("localhost")))) {
                throw new IllegalArgumentException();
            }
            // The gateway canonicalizes HTTP loopback to localhost. Both names
            // reach the same ADB tunnel; preserve the port and reject other hosts.
            if (scheme.equals("http") && host.equals("127.0.0.1")) host = "localhost";
            int port = uri.getPort();
            if (port == (scheme.equals("https") ? 443 : 80)) port = -1;
            return new URI(scheme, null, host, port, "/", null, null).toString();
        } catch (URISyntaxException | NullPointerException ex) {
            throw new IllegalArgumentException("Invalid dashboard address");
        }
    }

    public static boolean sameOrigin(String origin, String url) {
        try {
            URI uri = new URI(url);
            if (uri.getRawUserInfo() != null) return false;
            return origin.equals(parse(new URI(uri.getScheme(), null, uri.getHost(),
                    uri.getPort(), "/", null, null).toString()));
        } catch (URISyntaxException | IllegalArgumentException | NullPointerException ex) {
            return false;
        }
    }
}
