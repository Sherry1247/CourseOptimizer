package models;

import java.util.ArrayList;
import java.util.List;

/**
 * Semester class - Represents one semester's course schedule
 * 
 * Includes: - Semester identification (year, term) - List of courses -
 * Statistics (total credits, expected GPA)
 */
public class Semester {
    // ========== Semester Identification ==========
    private int year; // Year number, 1-4
    private String term; // "Fall" or "Spring"

    // ========== Course List ==========
    private List<Course> courses; // All courses in this semester

    // ========== Statistics ==========
    private int totalCredits; // Total credits
    private double expectedGPA; // Expected average GPA

    // ========== Constructors ==========

    /**
     * Basic constructor
     * 
     * @param year Year number (1-4)
     * @param term Semester term ("Fall" or "Spring")
     */
    public Semester(int year, String term) {
        this.year = year;
        this.term = term;
        this.courses = new ArrayList<>();
        this.totalCredits = 0;
        this.expectedGPA = 0.0;
    }

    // ========== Core Methods ==========

    /**
     * Add a course to this semester Automatically updates total credits and
     * recalculates GPA
     * 
     * @param course Course to add
     */
    public void addCourse(Course course) {
        if (course != null) {
            courses.add(course);
            totalCredits += course.getCredits();
            recalculateGPA();
        }
    }

    /**
     * Remove a course from this semester Automatically updates total credits and
     * recalculates GPA
     * 
     * @param courseId Course ID to remove
     * @return true if course was found and removed, false otherwise
     */
    public boolean removeCourse(String courseId) {
        Course toRemove = null;
        for (Course c : courses) {
            if (c.getCourseId().equals(courseId)) {
                toRemove = c;
                break;
            }
        }

        if (toRemove != null) {
            courses.remove(toRemove);
            totalCredits -= toRemove.getCredits();
            recalculateGPA();
            return true;
        }
        return false;
    }

    /**
     * Recalculate expected GPA based on current courses Called automatically when
     * courses are added/removed
     */
    private void recalculateGPA() {
        if (courses.isEmpty()) {
            expectedGPA = 0.0;
            return;
        }

        double totalGPA = 0.0;
        for (Course c : courses) {
            totalGPA += c.getAverageGPA();
        }
        expectedGPA = totalGPA / courses.size();
    }

    /**
     * Check if adding a course would exceed credit limit
     * 
     * @param course     Course to potentially add
     * @param maxCredits Maximum allowed credits
     * @return true if can add without exceeding limit, false otherwise
     */
    public boolean canAddCourse(Course course, int maxCredits) {
        return (totalCredits + course.getCredits()) <= maxCredits;
    }

    /**
     * Get number of courses in this semester
     * 
     * @return Course count
     */
    public int getCourseCount() {
        return courses.size();
    }

    /**
     * Check if semester contains a specific course
     * 
     * @param courseId Course ID to check
     * @return true if contains course, false otherwise
     */
    public boolean hasCourse(String courseId) {
        for (Course c : courses) {
            if (c.getCourseId().equals(courseId)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Get a specific course by ID
     * 
     * @param courseId Course ID
     * @return Course object if found, null otherwise
     */
    public Course getCourse(String courseId) {
        for (Course c : courses) {
            if (c.getCourseId().equals(courseId)) {
                return c;
            }
        }
        return null;
    }

    /**
     * Clear all courses from this semester
     */
    public void clearCourses() {
        courses.clear();
        totalCredits = 0;
        expectedGPA = 0.0;
    }

    // ========== Getters and Setters ==========

    public int getYear() {
        return year;
    }

    public void setYear(int year) {
        this.year = year;
    }

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public List<Course> getCourses() {
        return courses;
    }

    public void setCourses(List<Course> courses) {
        this.courses = courses;
        // Recalculate total credits and GPA
        totalCredits = 0;
        for (Course c : courses) {
            totalCredits += c.getCredits();
        }
        recalculateGPA();
    }

    public int getTotalCredits() {
        return totalCredits;
    }

    public void setTotalCredits(int totalCredits) {
        this.totalCredits = totalCredits;
    }

    public double getExpectedGPA() {
        return expectedGPA;
    }

    public void setExpectedGPA(double expectedGPA) {
        this.expectedGPA = expectedGPA;
    }

    // ========== Utility Methods ==========

    /**
     * Get semester label (e.g., "Year 1 - Fall")
     * 
     * @return Formatted semester label
     */
    public String getSemesterLabel() {
        return "Year " + year + " - " + term;
    }

    /**
     * Check if semester is empty (no courses)
     * 
     * @return true if no courses, false otherwise
     */
    public boolean isEmpty() {
        return courses.isEmpty();
    }

    /**
     * Get list of all course IDs in this semester
     * 
     * @return List of course IDs
     */
    public List<String> getCourseIds() {
        List<String> ids = new ArrayList<>();
        for (Course c : courses) {
            ids.add(c.getCourseId());
        }
        return ids;
    }

    public String toJson() {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"label\":\"").append(getSemesterLabel()).append("\",");

        sb.append("\"courses\":[");
        for (Course c : courses) {
            sb.append("{").append("\"id\":\"").append(c.getCourseId()).append("\",")
                    .append("\"name\":\"").append(c.getName()).append("\",").append("\"credits\":")
                    .append(c.getCredits()).append("},");
        }
        if (!courses.isEmpty())
            sb.deleteCharAt(sb.length() - 1);
        sb.append("]");

        sb.append("}");
        return sb.toString();
    }

    /**
     * toString method for easy debugging
     */
    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder();
        sb.append("\n========== ").append(getSemesterLabel()).append(" ==========\n");
        sb.append("Total Credits: ").append(totalCredits).append("\n");
        sb.append("Expected GPA: ").append(String.format("%.2f", expectedGPA)).append("\n");
        sb.append("Courses (").append(courses.size()).append("):\n");

        for (Course c : courses) {
            sb.append(String.format("  - %s: %s (%d credits)\n", c.getCourseId(), c.getName(),
                    c.getCredits()));
        }

        return sb.toString();
    }

    /**
     * Get a detailed summary of this semester
     */
    public String getDetailedSummary() {
        StringBuilder sb = new StringBuilder();
        sb.append("\n========== ").append(getSemesterLabel()).append(" ==========\n");
        sb.append("Total Credits: ").append(totalCredits).append("\n");
        sb.append("Expected GPA: ").append(String.format("%.2f", expectedGPA)).append("\n");
        sb.append("\nCourses:\n");

        for (Course c : courses) {
            sb.append(String.format("  %s: %s\n", c.getCourseId(), c.getName()));
            sb.append(String.format("    Credits: %d | Prof: %s (%.1f★) | A-rate: %.0f%%\n",
                    c.getCredits(), c.getProfessor(), c.getProfRating(), c.getARate() * 100));
        }

        return sb.toString();
    }
}
