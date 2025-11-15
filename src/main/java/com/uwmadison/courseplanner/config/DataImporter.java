package com.uwmadison.courseplanner.config;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uwmadison.courseplanner.entity.CourseEntity;
import com.uwmadison.courseplanner.repository.CourseRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * 数据导入配置类
 * 从JSON文件导入课程数据到数据库
 */
@Configuration
public class DataImporter {
    
    @Bean
    CommandLineRunner importData(CourseRepository repository) {
        return args -> {
            // 检查数据库是否已有数据
            if (repository.count() > 0) {
                System.out.println("Database already contains data. Skipping import.");
                return;
            }
            
            System.out.println("Starting data import...");
            
            try {
                // 读取JSON文件
                ObjectMapper mapper = new ObjectMapper();
                InputStream inputStream = new ClassPathResource("data/uw_madison_data.json").getInputStream();
                JsonNode rootNode = mapper.readTree(inputStream);
                
                // 解析courses数组
                JsonNode coursesNode = rootNode.get("courses");
                int count = 0;
                
                for (JsonNode courseNode : coursesNode) {
                    CourseEntity course = new CourseEntity();
                    
                    // 基本信息
                    course.setCourseCode(courseNode.get("full_code").asText());
                    course.setCourseName(courseNode.get("name").asText());
                    course.setCredits(courseNode.get("credits").asInt());
                    course.setDepartment(courseNode.get("department").asText());
                    
                    // 描述
                    if (courseNode.has("description")) {
                        course.setDescription(courseNode.get("description").asText());
                    }
                    
                    // 评分数据
                    if (courseNode.has("grade_a_rate")) {
                        course.setGradeARate(courseNode.get("grade_a_rate").asDouble());
                    }
                    if (courseNode.has("professor_rating")) {
                        course.setProfessorRating(courseNode.get("professor_rating").asDouble());
                    }
                    if (courseNode.has("difficulty")) {
                        course.setDifficulty(courseNode.get("difficulty").asInt());
                    }
                    
                    // 先修课程（转换为逗号分隔的字符串）
                    if (courseNode.has("prerequisites")) {
                        JsonNode prereqNode = courseNode.get("prerequisites");
                        List<String> prereqs = new ArrayList<>();
                        prereqNode.forEach(node -> prereqs.add(node.asText()));
                        course.setPrerequisites(String.join(",", prereqs));
                    }
                    
                    // 开课学期
                    if (courseNode.has("semesters")) {
                        JsonNode semestersNode = courseNode.get("semesters");
                        List<String> semesters = new ArrayList<>();
                        semestersNode.forEach(node -> semesters.add(node.asText()));
                        course.setSemesters(String.join(",", semesters));
                    }
                    
                    // 工作量
                    if (courseNode.has("typical_workload")) {
                        course.setTypicalWorkload(courseNode.get("typical_workload").asText());
                    }
                    
                    // 保存到数据库
                    repository.save(course);
                    count++;
                }
                
                System.out.println("✅ Successfully imported " + count + " courses!");
                
            } catch (Exception e) {
                System.err.println("❌ Error importing data: " + e.getMessage());
                e.printStackTrace();
            }
        };
    }
}
