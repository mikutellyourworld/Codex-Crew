package dev.codexcrew.mobile;

/** Validation shared by saved slots and automatic, one-way transport recovery. */
public final class ConnectionProfiles {
    private ConnectionProfiles() {}

    public static String validate(boolean https, String address) {
        String parsed = ConnectionAddress.parse(address);
        if (parsed.startsWith("https://") != https) throw new IllegalArgumentException();
        return parsed;
    }

    public static String fallback(String active, String savedHttps) {
        try {
            validate(false, active);
            return validate(true, savedHttps);
        } catch (IllegalArgumentException ex) {
            return null;
        }
    }

    public static final class Health {
        private int failures;
        public boolean record(boolean reachable) {
            failures = reachable ? 0 : Math.min(2, failures + 1);
            return failures >= 2;
        }
    }
}
