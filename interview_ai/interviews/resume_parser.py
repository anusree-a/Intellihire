"""
Resume Parser Utility
Extracts skills, experience, and key information from uploaded resumes
"""

import re
import PyPDF2
from docx import Document
import anthropic
from django.conf import settings


class ResumeParser:
    """
    Utility class to parse resumes and extract structured information
    Supports PDF and DOCX formats
    """
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    def parse_resume(self, file_path):
        """
        Main method to parse resume and return structured data
        """
        # Extract text from file
        text = self._extract_text(file_path)
        
        if not text:
            return {
                'error': 'Could not extract text from resume',
                'skills': [],
                'experience_summary': 'N/A',
                'education': 'N/A'
            }
        
        # Use AI to structure the resume data
        structured_data = self._ai_parse(text)
        
        return structured_data
    
    def _extract_text(self, file_path):
        """Extract text from PDF or DOCX"""
        try:
            if file_path.endswith('.pdf'):
                return self._extract_from_pdf(file_path)
            elif file_path.endswith('.docx'):
                return self._extract_from_docx(file_path)
            else:
                return ""
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""
    
    def _extract_from_pdf(self, file_path):
        """Extract text from PDF"""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text()
        except Exception as e:
            print(f"PDF extraction error: {e}")
        return text
    
    def _extract_from_docx(self, file_path):
        """Extract text from DOCX"""
        text = ""
        try:
            doc = Document(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        except Exception as e:
            print(f"DOCX extraction error: {e}")
        return text
    
    def _ai_parse(self, resume_text):
        """Use Claude to intelligently parse resume content"""
        
        prompt = f"""Analyze this resume and extract structured information in JSON format.

RESUME TEXT:
{resume_text[:3000]}  

Please extract and return ONLY a JSON object with these fields:
{{
    "skills": ["skill1", "skill2", ...],  // Technical and soft skills
    "experience_summary": "Brief summary of work experience",
    "education": "Highest degree and institution",
    "years_of_experience": number,
    "current_role": "Most recent job title",
    "key_projects": ["project1", "project2"],
    "certifications": ["cert1", "cert2"],
    "languages": ["language1", "language2"]
}}

Be thorough but concise. Return only the JSON, no other text.
"""
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
            
            import json
            result_text = response.content[0].text
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                parsed_data = json.loads(json_match.group())
                return parsed_data
            else:
                return self._fallback_parse(resume_text)
                
        except Exception as e:
            print(f"AI parsing error: {e}")
            return self._fallback_parse(resume_text)
    
    def _fallback_parse(self, text):
        """Simple regex-based fallback parsing"""
        
        # Extract skills (common keywords)
        skill_keywords = [
            'Python', 'Java', 'JavaScript', 'C++', 'SQL', 'Django', 'React',
            'AWS', 'Docker', 'Machine Learning', 'AI', 'Data Science',
            'HTML', 'CSS', 'Node.js', 'MongoDB', 'PostgreSQL', 'Git',
            'Agile', 'Scrum', 'Leadership', 'Communication', 'Problem Solving'
        ]
        
        found_skills = []
        text_lower = text.lower()
        for skill in skill_keywords:
            if skill.lower() in text_lower:
                found_skills.append(skill)
        
        # Extract email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        email = email_match.group() if email_match else "N/A"
        
        # Extract phone
        phone_match = re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', text)
        phone = phone_match.group() if phone_match else "N/A"
        
        return {
            'skills': found_skills[:15],  # Limit to 15 skills
            'experience_summary': 'Experience details found in resume',
            'education': 'Education details found in resume',
            'years_of_experience': 0,
            'current_role': 'N/A',
            'key_projects': [],
            'certifications': [],
            'languages': ['English'],
            'contact': {
                'email': email,
                'phone': phone
            }
        }


def parse_resume_for_session(session):
    """
    Helper function to parse resume for an interview session
    """
    if not session.resume:
        return None
    
    parser = ResumeParser()
    file_path = session.resume.path
    
    parsed_data = parser.parse_resume(file_path)
    
    # Store in session
    session.parsed_resume_data = parsed_data
    session.save()
    
    return parsed_data