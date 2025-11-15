import models.*;
import optimizer.ScheduleOptimizer;
import java.util.*;

/**
 * Main class - Test the course optimization algorithm
 * 
 * This creates sample data and demonstrates the optimizer's functionality
 */
public class Main {
    

    public static void main(String[] args) {
        System.out.println("Course Planner - Algorithm Test");
        System.out.println("=".repeat(60));

        // Run different test scenarios
        System.out.println("\n【 TEST 1: Single Major (CS) 】\n");
        testSingleMajor();

        System.out.println("\n\n" + "=".repeat(60));
        System.out.println("\n【 TEST 2: Double Major (CS + MATH) 】\n");
        testDoubleMajor();
    }

    // ========== Test 1: Single Major ==========

    /**
     * Test single major planning (CS only)
     */
    private static void testSingleMajor() {
        // 1. Create test courses
        List<Course> allCourses = createTestCourses();
        System.out.println("Created " + allCourses.size() + " test courses");

        // 2. Create student profile
        StudentProfile student = new StudentProfile();
        student.setMajor("CS");
        student.setGpaGoal(3.5);
        student.setMaxCreditsPerSem(15);
        student.setNoEarlyClass(true);
        student.setPrioritizeGPA(true);
        student.setBalanceDifficulty(true);
        student.setCareerGoal("grad_school");

        System.out.println("Student profile: " + student);

        // 3. Generate plan
        ScheduleOptimizer optimizer = new ScheduleOptimizer();
        List<Semester> plan = optimizer.generatePlan(student, allCourses);

        // 4. Print results
        optimizer.printDetailedPlan(plan);
        optimizer.printPlanStatistics(plan);

        // 5. Print summary
        System.out.println("\n" + optimizer.generateSummaryReport(plan, student));
    }

    // ========== Test 2: Double Major ==========

    /**
     * Test double major planning (CS + MATH)
     */
    private static void testDoubleMajor() {
        // 1. Create enhanced courses (with overlap courses)
        List<Course> allCourses = createEnhancedTestCourses();
        System.out.println("Created " + allCourses.size() + " test courses");

        // 2. Create student profile for double major
        StudentProfile student = new StudentProfile();
        student.setMajor("CS");
        student.setSecondMajor("MATH"); // Double major!
        student.setGpaGoal(3.3);
        student.setMaxCreditsPerSem(16); // Take a bit more credits
        student.setNoEarlyClass(false); // OK with early classes
        student.setPrioritizeGPA(false);
        student.setBalanceDifficulty(true);
        student.setCareerGoal("grad_school");

        System.out.println("Student profile: " + student);

        // 3. Generate plan
        ScheduleOptimizer optimizer = new ScheduleOptimizer();
        List<Semester> plan = optimizer.generatePlan(student, allCourses);

        // 4. Print results
        optimizer.printDetailedPlan(plan);
        optimizer.printPlanStatistics(plan);

        // 5. Print summary
        System.out.println("\n" + optimizer.generateSummaryReport(plan, student));
    }

    // ========== Test Data Creation ==========

    /**
     * Create basic test courses for single major test
     * 
     * @return List of courses
     */
    private static List<Course> createTestCourses() {
        List<Course> courses = new ArrayList<>();

        // ===== CS Courses =====

        // CS 200 - Entry level, no prerequisites
        Course cs200 = new Course("CS 200", "Programming I", 3);
        cs200.setPrerequisites(new ArrayList<>());
        cs200.setAverageGPA(3.2);
        cs200.setARate(0.75);
        cs200.setProfessor("Prof. Smith");
        cs200.setProfRating(4.5);
        cs200.setEarlyMorning(false);
        cs200.setRelevance("both");
        cs200.addMajor("CS");
        courses.add(cs200);

        // CS 300 - Requires CS 200
        Course cs300 = new Course("CS 300", "Programming II", 3);
        cs300.setPrerequisites(Arrays.asList("CS 200"));
        cs300.setAverageGPA(3.0);
        cs300.setARate(0.70);
        cs300.setProfessor("Prof. Johnson");
        cs300.setProfRating(4.2);
        cs300.setEarlyMorning(false);
        cs300.setRelevance("both");
        cs300.addMajor("CS");
        courses.add(cs300);

        // CS 400 - Requires CS 300
        Course cs400 = new Course("CS 400", "Programming III", 3);
        cs400.setPrerequisites(Arrays.asList("CS 300"));
        cs400.setAverageGPA(2.9);
        cs400.setARate(0.65);
        cs400.setProfessor("Prof. Williams");
        cs400.setProfRating(4.8);
        cs400.setEarlyMorning(true); // Early morning class
        cs400.setRelevance("grad_school");
        cs400.addMajor("CS");
        courses.add(cs400);

        // CS 500 - Requires CS 400
        Course cs500 = new Course("CS 500", "Operating Systems", 3);
        cs500.setPrerequisites(Arrays.asList("CS 400"));
        cs500.setAverageGPA(2.8);
        cs500.setARate(0.60);
        cs500.setProfessor("Prof. Davis");
        cs500.setProfRating(3.9);
        cs500.setEarlyMorning(false);
        cs500.setRelevance("industry");
        cs500.addMajor("CS");
        courses.add(cs500);

        // CS 354 - Requires CS 300
        Course cs354 = new Course("CS 354", "Machine Organization", 3);
        cs354.setPrerequisites(Arrays.asList("CS 300"));
        cs354.setAverageGPA(2.7);
        cs354.setARate(0.55);
        cs354.setProfessor("Prof. Martinez");
        cs354.setProfRating(4.0);
        cs354.setEarlyMorning(false);
        cs354.setRelevance("both");
        cs354.addMajor("CS");
        courses.add(cs354);

        // CS 577 - Requires CS 400
        Course cs577 = new Course("CS 577", "Algorithms", 3);
        cs577.setPrerequisites(Arrays.asList("CS 400"));
        cs577.setAverageGPA(2.7);
        cs577.setARate(0.55);
        cs577.setProfessor("Prof. Brown");
        cs577.setProfRating(4.1);
        cs577.setEarlyMorning(false);
        cs577.setRelevance("grad_school");
        cs577.addMajor("CS");
        courses.add(cs577);

        // ===== Math Courses =====

        // MATH 221 - No prerequisites
        Course math221 = new Course("MATH 221", "Calculus I", 5);
        math221.setPrerequisites(new ArrayList<>());
        math221.setAverageGPA(2.9);
        math221.setARate(0.55);
        math221.setProfessor("Prof. Taylor");
        math221.setProfRating(3.8);
        math221.setEarlyMorning(true);
        math221.setRelevance("both");
        math221.addMajor("CS");
        math221.addMajor("MATH");
        courses.add(math221);

        // MATH 222 - Requires MATH 221
        Course math222 = new Course("MATH 222", "Calculus II", 4);
        math222.setPrerequisites(Arrays.asList("MATH 221"));
        math222.setAverageGPA(2.8);
        math222.setARate(0.50);
        math222.setProfessor("Prof. Anderson");
        math222.setProfRating(3.5);
        math222.setEarlyMorning(false);
        math222.setRelevance("both");
        math222.addMajor("CS");
        math222.addMajor("MATH");
        courses.add(math222);

        // MATH 340 - Requires MATH 222
        Course math340 = new Course("MATH 340", "Linear Algebra", 3);
        math340.setPrerequisites(Arrays.asList("MATH 222"));
        math340.setAverageGPA(3.1);
        math340.setARate(0.68);
        math340.setProfessor("Prof. Wilson");
        math340.setProfRating(4.3);
        math340.setEarlyMorning(false);
        math340.setRelevance("grad_school");
        math340.addMajor("CS");
        math340.addMajor("MATH");
        courses.add(math340);

        return courses;
    }

    /**
     * Create enhanced test courses for double major test Includes more courses and
     * overlap courses
     * 
     * @return List of courses
     */
    private static List<Course> createEnhancedTestCourses() {
        // Start with basic courses
        List<Course> courses = createTestCourses();

        // Add more MATH courses

        // MATH 234 - Requires MATH 222
        Course math234 = new Course("MATH 234", "Calculus III", 4);
        math234.setPrerequisites(Arrays.asList("MATH 222"));
        math234.setAverageGPA(3.0);
        math234.setARate(0.60);
        math234.setProfessor("Prof. Lee");
        math234.setProfRating(4.0);
        math234.setEarlyMorning(false);
        math234.setRelevance("both");
        math234.addMajor("MATH");
        courses.add(math234);

        // MATH 341 - Requires MATH 340
        Course math341 = new Course("MATH 341", "Real Analysis", 3);
        math341.setPrerequisites(Arrays.asList("MATH 340"));
        math341.setAverageGPA(2.6);
        math341.setARate(0.45);
        math341.setProfessor("Prof. Garcia");
        math341.setProfRating(3.9);
        math341.setEarlyMorning(false);
        math341.setRelevance("grad_school");
        math341.addMajor("MATH");
        courses.add(math341);

        // MATH 421 - Requires MATH 341
        Course math421 = new Course("MATH 421", "Advanced Analysis", 3);
        math421.setPrerequisites(Arrays.asList("MATH 341"));
        math421.setAverageGPA(2.8);
        math421.setARate(0.50);
        math421.setProfessor("Prof. Chen");
        math421.setProfRating(4.2);
        math421.setEarlyMorning(false);
        math421.setRelevance("grad_school");
        math421.addMajor("MATH");
        courses.add(math421);

        // Add more CS courses

        // CS 540 - Requires CS 400
        Course cs540 = new Course("CS 540", "Artificial Intelligence", 3);
        cs540.setPrerequisites(Arrays.asList("CS 400"));
        cs540.setAverageGPA(3.0);
        cs540.setARate(0.65);
        cs540.setProfessor("Prof. Zhang");
        cs540.setProfRating(4.6);
        cs540.setEarlyMorning(false);
        cs540.setRelevance("grad_school");
        cs540.addMajor("CS");
        courses.add(cs540);

        return courses;
    }
}
