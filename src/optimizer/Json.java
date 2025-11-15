package optimizer;

import models.*;
import java.util.*;

public class Json {

    // ======================================================
    // Public: Parse raw JSON string → Map
    // ======================================================
    public static Map<String, Object> parse(String json) {
        return simpleParse(json);
    }

    // ======================================================
    // Public: Convert Map → StudentProfile
    // ======================================================
    public static StudentProfile toStudentProfile(Map<String, Object> map) {
        StudentProfile p = new StudentProfile();

        p.setMajor(safeString(map.get("major1")));
        p.setSecondMajor(safeString(map.get("major2")));

        // majorType = "double" ?
        p.setDoubleMajor("double".equals(safeString(map.get("majorType"))));

        // numbers
        p.setGpaGoal(parseDouble(map.get("targetGPA"), 3.0));
        p.setMaxCreditsPerSem(parseInt(map.get("maxCredits"), 15));

        // preferences
        p.setNoEarlyClass(parseBoolean(map.get("avoid8am")));
        p.setPrioritizeGPA(parseBoolean(map.get("prioritizeGPA")));
        p.setBalanceDifficulty(parseBoolean(map.get("balanceDifficulty")));
        p.setCareerGoal(safeString(map.get("careerGoal")));

        // completedCourses
        Set<String> completedSet = new HashSet<>();
        Object completedObj = map.get("completedCourses");
        if (completedObj instanceof List) {
            completedSet.addAll((List<String>) completedObj);
        }
        p.setCompletedCourses(completedSet);

        return p;
    }

    // ======================================================
    // Lightweight JSON object/array parser (no external libs)
    // ======================================================
    public static Map<String, Object> simpleParse(String json) {
        Map<String, Object> map = new HashMap<>();

        json = json.trim();
        if (json.startsWith("{"))
            json = json.substring(1);
        if (json.endsWith("}"))
            json = json.substring(0, json.length() - 1);

        // split top-level key-value by commas
        List<String> parts = splitTopLevel(json);

        for (String part : parts) {
            String[] kv = part.split(":", 2);
            if (kv.length < 2)
                continue;

            String key = kv[0].trim().replace("\"", "");
            String raw = kv[1].trim();

            // null
            if (raw.equals("null")) {
                map.put(key, null);
                continue;
            }

            // string array
            if (raw.startsWith("[")) {
                map.put(key, parseStringArray(raw));
                continue;
            }

            // number
            if (raw.matches("-?\\d+(\\.\\d+)?")) {
                if (raw.contains(".")) {
                    map.put(key, Double.parseDouble(raw));
                } else {
                    map.put(key, Integer.parseInt(raw));
                }
                continue;
            }

            // string with quotes
            raw = raw.replace("\"", "");
            map.put(key, raw);
        }

        return map;
    }

    // ======================================================
    // Helper: split top-level JSON by commas
    // ======================================================
    private static List<String> splitTopLevel(String json) {
        List<String> list = new ArrayList<>();
        StringBuilder sb = new StringBuilder();
        int depth = 0;

        for (char c : json.toCharArray()) {
            if (c == '[')
                depth++;
            if (c == ']')
                depth--;

            if (c == ',' && depth == 0) {
                list.add(sb.toString());
                sb.setLength(0);
            } else {
                sb.append(c);
            }
        }

        if (sb.length() > 0)
            list.add(sb.toString());
        return list;
    }

    // ======================================================
    // Helper: parse ["A","B","C"]
    // ======================================================
    private static List<String> parseStringArray(String raw) {
        List<String> list = new ArrayList<>();
        raw = raw.substring(1, raw.length() - 1).trim(); // remove [ ]

        if (raw.isEmpty())
            return list;

        for (String s : splitTopLevelArray(raw)) {
            s = s.trim().replace("\"", "");
            if (!s.isEmpty())
                list.add(s);
        }
        return list;
    }

    // split array items
    private static List<String> splitTopLevelArray(String json) {
        List<String> list = new ArrayList<>();
        StringBuilder sb = new StringBuilder();
        int depth = 0;

        for (char c : json.toCharArray()) {
            if (c == '[')
                depth++;
            if (c == ']')
                depth--;

            if (c == ',' && depth == 0) {
                list.add(sb.toString());
                sb.setLength(0);
            } else {
                sb.append(c);
            }
        }

        if (sb.length() > 0)
            list.add(sb.toString());
        return list;
    }

    // ======================================================
    // Basic safe conversion helpers
    // ======================================================
    private static String safeString(Object o) {
        return o == null ? null : o.toString();
    }

    private static int parseInt(Object o, int defaultVal) {
        if (o == null)
            return defaultVal;
        try {
            return Integer.parseInt(o.toString());
        } catch (Exception e) {
            return defaultVal;
        }
    }

    private static double parseDouble(Object o, double defaultVal) {
        if (o == null)
            return defaultVal;
        try {
            return Double.parseDouble(o.toString());
        } catch (Exception e) {
            return defaultVal;
        }
    }

    private static boolean parseBoolean(Object o) {
        if (o == null)
            return false;
        String s = o.toString().toLowerCase();
        return s.equals("true") || s.equals("1") || s.equals("yes");
    }

    // ======================================================
    // Convert plan → JSON
    // ======================================================
    public static String planToJson(List<Semester> plan) {
        StringBuilder sb = new StringBuilder();
        sb.append("[");

        for (Semester sem : plan) {
            sb.append(sem.toJson()).append(",");
        }

        if (plan.size() > 0)
            sb.deleteCharAt(sb.length() - 1);
        sb.append("]");

        return sb.toString();
    }
}
