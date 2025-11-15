package optimizer;

import models.*;
import java.util.*;

public class Json {

    public static Map<String, Object> parse(String json) {
        return simpleParse(json);
    }

    public static StudentProfile toStudentProfile(Map<String, Object> map) {
        StudentProfile p = new StudentProfile();

        p.setMajor((String) map.get("major1"));
        p.setSecondMajor((String) map.get("major2"));
        p.setDoubleMajor("double".equals(map.get("majorType")));

        p.setGpaGoal(Double.parseDouble(map.get("targetGPA").toString()));
        p.setMaxCreditsPerSem(Integer.parseInt(map.get("maxCredits").toString()));

        List<String> completed = (List<String>) map.get("completedCourses");
        p.setCompletedCourses(new HashSet<>(completed));

        return p;
    }
    
    public static Map<String, Object> simpleParse(String json) {
        Map<String, Object> map = new HashMap<>();

        json = json.trim();
        if (json.startsWith("{")) json = json.substring(1);
        if (json.endsWith("}")) json = json.substring(0, json.length() - 1);

        // 按逗号分割 key:value
        String[] parts = json.split(",");

        for (String part : parts) {
            String[] kv = part.split(":");

            if (kv.length < 2) continue;

            String key = kv[0].trim().replace("\"", "");

            // 去掉前后引号
            String value = kv[1].trim();
            value = value.replace("\"", "");

            map.put(key, value);
        }

        return map;
    }


    public static String planToJson(List<Semester> plan) {
        StringBuilder sb = new StringBuilder();
        sb.append("[");
        for (Semester sem : plan) {
            sb.append(sem.toJson()).append(",");
        }
        if (plan.size() > 0) sb.deleteCharAt(sb.length() - 1);
        sb.append("]");
        return sb.toString();
    }
}

