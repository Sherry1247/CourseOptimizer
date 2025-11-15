package models;

import java.util.*;

public class CourseRepository {

    public static List<Course> loadAllCourses() {
        List<Course> list = new ArrayList<>();

        // TODO：之后可以从 JSON 或数据库加载
        // demo只是方便跑通前后端

        list.add(new Course("CS200", "Programming I", 3));
        list.add(new Course("CS300", "Programming II", 3, List.of("CS200"), 3.3, 0.60, "Prof A", 4.0, false, ""));
        list.add(new Course("CS400", "Programming III", 3, List.of("CS300"), 3.1, 0.55, "Prof B", 3.9, false, ""));

        list.add(new Course("MATH221", "Calculus I", 5));
        list.add(new Course("MATH222", "Calculus II", 4, List.of("MATH221"), 3.0, 0.50, "Prof C", 4.3, false, ""));

        return list;
    }
}
