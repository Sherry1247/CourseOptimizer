package models;

import java.util.ArrayList;
import java.util.List;

/**
 * Course class - Stores all information about a course
 * 
 * Includes: - Basic info (course ID, name, credits) - Prerequisites - Grade
 * statistics (average GPA, A-rate) - Professor information - Course attributes
 * (early morning, relevance, majors)
 */
public class Course {
    // ========== Basic Information ==========
    private String courseId; // Course ID, e.g., "CS 400"
    private String name; // Course name, e.g., "Programming III"
    private int credits; // Credits, e.g., 3

    // ========== Prerequisites ==========
    private List<String> prerequisites; // List of prerequisite courses, e.g., ["CS 300", "CS 220"]

    // ========== Grade Statistics ==========
    private double averageGPA; // Historical average GPA, e.g., 3.2
    private double aRate; // A-rate (proportion getting A), e.g., 0.75 (75%)

    // ========== Professor Information ==========
    private String professor; // Professor name, e.g., "Prof. Smith"
    private double profRating; // Rate My Professor rating, 1.0-5.0

    // ========== Course Attributes ==========
    private boolean isEarlyMorning; // Is it an 8am class, true/false
    private String relevance; // Relevance: "grad_school" or "industry" or "both"

    // ========== Major Attribution (for double major support) ==========
    private List<String> belongsToMajors; // Which majors this course belongs to, e.g., ["CS",
                                          // "MATH"]

    // ========== Constructors ==========

    /**
     * Basic constructor (required information only)
     * 
     * @param courseId Course ID
     * @param name     Course name
     * @param credits  Number of credits
     */
    public Course(String courseId, String name, int credits) {
        this.courseId = courseId;
        this.name = name;
        this.credits = credits;
        this.prerequisites = new ArrayList<>();
        this.belongsToMajors = new ArrayList<>();
    }

    /**
     * Full constructor
     */
    public Course(String courseId, String name, int credits, List<String> prerequisites,
            double averageGPA, double aRate, String professor, double profRating,
            boolean isEarlyMorning, String relevance) {
        this.courseId = courseId;
        this.name = name;
        this.credits = credits;
        this.prerequisites = prerequisites != null ? prerequisites : new ArrayList<>();
        this.averageGPA = averageGPA;
        this.aRate = aRate;
        this.professor = professor;
        this.profRating = profRating;
        this.isEarlyMorning = isEarlyMorning;
        this.relevance = relevance;
        this.belongsToMajors = new ArrayList<>();
    }

    // ========== Getters and Setters ==========

    public String getCourseId() {
        return courseId;
    }

    public void setCourseId(String courseId) {
        this.courseId = courseId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getCredits() {
        return credits;
    }

    public void setCredits(int credits) {
        this.credits = credits;
    }

    public List<String> getPrerequisites() {
        return prerequisites;
    }

    public void setPrerequisites(List<String> prerequisites) {
        this.prerequisites = prerequisites;
    }

    public double getAverageGPA() {
        return averageGPA;
    }

    public void setAverageGPA(double averageGPA) {
        this.averageGPA = averageGPA;
    }

    public double getARate() {
        return aRate;
    }

    public void setARate(double aRate) {
        this.aRate = aRate;
    }

    public String getProfessor() {
        return professor;
    }

    public void setProfessor(String professor) {
        this.professor = professor;
    }

    public double getProfRating() {
        return profRating;
    }

    public void setProfRating(double profRating) {
        this.profRating = profRating;
    }

    public boolean isEarlyMorning() {
        return isEarlyMorning;
    }

    public void setEarlyMorning(boolean earlyMorning) {
        isEarlyMorning = earlyMorning;
    }

    public String getRelevance() {
        return relevance;
    }

    public void setRelevance(String relevance) {
        this.relevance = relevance;
    }

    public List<String> getBelongsToMajors() {
        return belongsToMajors;
    }

    public void setBelongsToMajors(List<String> belongsToMajors) {
        this.belongsToMajors = belongsToMajors;
    }

    // ========== Utility Methods ==========

    /**
     * Check if course has prerequisites
     * 
     * @return true if has prerequisites, false otherwise
     */
    public boolean hasPrerequisites() {
        return prerequisites != null && !prerequisites.isEmpty();
    }

    /**
     * Add a prerequisite course
     * 
     * @param courseId Prerequisite course ID
     */
    public void addPrerequisite(String courseId) {
        if (prerequisites == null) {
            prerequisites = new ArrayList<>();
        }
        prerequisites.add(courseId);
    }

    /**
     * Add a major that this course belongs to
     * 
     * @param major Major name (e.g., "CS", "MATH")
     */
    public void addMajor(String major) {
        if (belongsToMajors == null) {
            belongsToMajors = new ArrayList<>();
        }
        if (!belongsToMajors.contains(major)) {
            belongsToMajors.add(major);
        }
    }

    /**
     * Check if course belongs to a specific major
     * 
     * @param major Major name
     * @return true if belongs to this major, false otherwise
     */
    public boolean belongsToMajor(String major) {
        return belongsToMajors != null && belongsToMajors.contains(major);
    }

    /**
     * Check if course is an overlap course (belongs to multiple majors) Useful for
     * double major students
     * 
     * @param majors List of majors to check
     * @return true if belongs to 2 or more of the given majors
     */
    public boolean isOverlapCourse(List<String> majors) {
        if (belongsToMajors == null || belongsToMajors.isEmpty()) {
            return false;
        }

        int matchCount = 0;
        for (String major : majors) {
            if (belongsToMajors.contains(major)) {
                matchCount++;
            }
        }

        return matchCount >= 2; // Belongs to at least 2 majors
    }

    /**
     * toString method for easy debugging
     */
    @Override
    public String toString() {
        return String.format("%s: %s (%d credits, GPA: %.2f, A-rate: %.0f%%, Prof: %s)", courseId,
                name, credits, averageGPA, aRate * 100, professor);
    }

    /**
     * Detailed string representation
     */
    public String toDetailedString() {
        StringBuilder sb = new StringBuilder();
        sb.append("Course: ").append(courseId).append(" - ").append(name).append("\n");
        sb.append("  Credits: ").append(credits).append("\n");
        sb.append("  Prerequisites: ").append(prerequisites.isEmpty() ? "None" : prerequisites)
                .append("\n");
        sb.append("  Average GPA: ").append(String.format("%.2f", averageGPA)).append("\n");
        sb.append("  A-Rate: ").append(String.format("%.0f%%", aRate * 100)).append("\n");
        sb.append("  Professor: ").append(professor).append(" (Rating: ").append(profRating)
                .append(")").append("\n");
        sb.append("  Early Morning: ").append(isEarlyMorning ? "Yes" : "No").append("\n");
        sb.append("  Relevance: ").append(relevance != null ? relevance : "N/A").append("\n");
        sb.append("  Belongs to majors: ")
                .append(belongsToMajors.isEmpty() ? "N/A" : belongsToMajors);
        return sb.toString();
    }
}