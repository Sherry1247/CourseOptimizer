package models;

import java.util.ArrayList;
import java.util.List;

/**
 * 课程类 - 存储一门课的所有信息
 */
public class Course {
    // ========== 基本信息 ==========
    private String courseId;
    private String name;
    private int credits;

    // ========== 先修课程 ==========
    private List<String> prerequisites;

    // ========== 成绩相关 ==========
    private double averageGPA;
    private double aRate;

    // ========== 教授信息 ==========
    private String professor;
    private double profRating;

    // ========== 课程属性 ==========
    private boolean isEarlyMorning;
    private String relevance;

    // ========== 🆕 专业信息（支持双专业）==========
    private List<String> majors; // 这门课属于哪些专业

    // ========== 构造函数 ==========

    public Course(String courseId, String name, int credits) {
        this.courseId = courseId;
        this.name = name;
        this.credits = credits;
        this.prerequisites = new ArrayList<>();
        this.majors = new ArrayList<>(); // 🆕 初始化专业列表
    }

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
        this.majors = new ArrayList<>(); // 🆕 初始化专业列表
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

    // ========== 🆕 专业相关方法 ==========

    public List<String> getMajors() {
        return majors;
    }

    public void setMajors(List<String> majors) {
        this.majors = majors;
    }

    /**
     * 添加一个专业
     */
    public void addMajor(String major) {
        if (majors == null) {
            majors = new ArrayList<>();
        }
        if (!majors.contains(major)) {
            majors.add(major);
        }
    }

    /**
     * 检查这门课是否属于某个专业
     */
    public boolean belongsToMajor(String major) {
        return majors != null && majors.contains(major);
    }

    /**
     * 检查这门课是否是重叠课程（属于多个专业）
     */
    public boolean isOverlapCourse(List<String> studentMajors) {
        if (majors == null || majors.isEmpty() || studentMajors == null) {
            return false;
        }

        int count = 0;
        for (String major : studentMajors) {
            if (majors.contains(major)) {
                count++;
            }
        }

        return count >= 2; // 属于学生的2个或以上专业
    }

    // ========== 工具方法 ==========

    public boolean hasPrerequisites() {
        return prerequisites != null && !prerequisites.isEmpty();
    }

    public void addPrerequisite(String courseId) {
        if (prerequisites == null) {
            prerequisites = new ArrayList<>();
        }
        prerequisites.add(courseId);
    }

    @Override
    public String toString() {
        return String.format("%s: %s (%d credits, GPA: %.2f, A-rate: %.0f%%, Prof: %s)", courseId,
                name, credits, averageGPA, aRate * 100, professor);
    }
}