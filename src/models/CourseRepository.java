package models;

import java.util.*;

public class CourseRepository {

    public static List<Course> loadAllCourses() {
        List<Course> list = new ArrayList<>();

        // ===== CS COURSES =====

        // CS 200 - no prereq
        list.add(new Course("CS 200", "Programming I", 3));

        // CS 300 - prereq CS 200
        list.add(new Course("CS 300", "Programming II", 3, List.of("CS 200"), 3.3, 0.60, "Prof A",
                4.0, false, ""));

        // CS 400 - prereq CS 300
        list.add(new Course("CS 400", "Programming III", 3, List.of("CS 300"), 3.1, 0.55, "Prof B",
                3.9, false, ""));

        // CS 500 - prereq CS 400
        list.add(new Course("CS 500", "Operating Systems", 3, List.of("CS 400"), 3.0, 0.50,
                "Prof C", 4.0, false, ""));

        // CS 354 - prereq CS 300
        list.add(new Course("CS 354", "Machine Organization", 3, List.of("CS 300"), 2.8, 0.45,
                "Prof D", 4.1, false, ""));

        // CS 577 - prereq CS 400
        list.add(new Course("CS 577", "Algorithms", 3, List.of("CS 400"), 2.7, 0.40, "Prof E", 4.2,
                false, ""));

        // CS 540 - prereq CS 400
        list.add(new Course("CS 540", "Artificial Intelligence", 3, List.of("CS 400"), 3.2, 0.65,
                "Prof F", 4.5, false, ""));

        // ===== MATH COURSES =====

        // MATH 221 - no prereq
        list.add(new Course("MATH 221", "Calculus I", 5));

        // MATH 222 - prereq MATH 221
        list.add(new Course("MATH 222", "Calculus II", 4, List.of("MATH 221"), 3.0, 0.50, "Prof G",
                4.3, false, ""));

        // MATH 340 - prereq MATH 222
        list.add(new Course("MATH 340", "Linear Algebra", 3, List.of("MATH 222"), 3.4, 0.60,
                "Prof H", 4.1, false, ""));

        return list;
    }
}
