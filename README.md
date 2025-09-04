# Resume Optimization Extension Backend

A Flask-based backend API for the Resume Optimization Chrome Extension that helps users optimize their resumes for specific job postings.

## Features

### Core Functionality

1. **Resume Upload & Processing** - Upload and parse resume files into structured YAML format
2. **Job Description Extraction** - Extract job descriptions and required skills from job posting URLs
3. **Compatibility Analysis** - Compare resume with job requirements and generate match scores
4. **Resume Optimization** - Enhance resume content based on job requirements
5. **Resume Generation** - Generate professional PDF/DOCX resumes using optimized data
6. **Chrome Extension Integration** - Specialized endpoints for browser extension

### API Endpoints

#### Main Endpoints

- `POST /api/upload-resume` - Upload and process resume file
- `POST /api/job-description` - Extract job description from URL
- `POST /api/analyze-compatibility` - Analyze resume-job compatibility
- `POST /api/optimize-resume` - Optimize resume for specific job
- `POST /api/generate-resume` - Generate final resume document
- `GET /api/user-resumes/<user_id>` - Get user's resume versions
- `GET /download/<filename>` - Download generated resume

#### Chrome Extension Endpoints

- `POST /api/extension/analyze` - Quick analysis from job URL
- `POST /api/extension/optimize` - Quick resume optimization
- `POST /api/extension/generate` - Quick resume generation

## Setup

### Prerequisites

- Python 3.8+
- OpenAI API key
- Groq API key

### Installation

1. Clone the repository
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your API keys:

   ```
   OPENAI_API_KEY=your_openai_api_key_here
   GROQ_API_KEY=your_groq_api_key_here
   ```

4. Run the application:
   ```bash
   python app.py
   ```

The server will start on `http://localhost:5000`

## Usage

### Upload Resume

```bash
curl -X POST http://localhost:5000/api/upload-resume \
  -F "file=@resume.pdf" \
  -F "user_id=user123"
```

### Extract Job Description

```bash
curl -X POST http://localhost:5000/api/job-description \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/job-posting"}'
```

### Analyze Compatibility

```bash
curl -X POST http://localhost:5000/api/analyze-compatibility \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "job_description": "Software Engineer position...",
    "skills": ["Python", "JavaScript", "React"]
  }'
```

## TODO Items

### High Priority

1. **Resume Parsing Implementation**

   - Implement PDF parsing using PyPDF2 or pdfplumber
   - Implement DOCX parsing using python-docx
   - Add text file parsing support
   - Use LLM to extract structured data from parsed text

2. **Database Integration**

   - Replace in-memory storage with proper database
   - Implement user authentication and session management
   - Add data persistence and backup

3. **File Management**
   - Implement proper file serving with authentication
   - Add file cleanup and storage management
   - Add file format validation

### Medium Priority

1. **Error Handling**

   - Add comprehensive error handling and logging
   - Implement proper HTTP status codes
   - Add input validation and sanitization

2. **Performance Optimization**

   - Add caching for frequently accessed data
   - Implement rate limiting
   - Optimize LLM calls and responses

3. **Security**
   - Add authentication and authorization
   - Implement file upload security
   - Add API key validation

### Low Priority

1. **Additional Features**

   - Add resume templates and formatting options
   - Implement batch processing
   - Add analytics and usage tracking

2. **Documentation**
   - Add API documentation with Swagger/OpenAPI
   - Create user guides and tutorials
   - Add code documentation

## File Structure

```
├── app.py                 # Main Flask application
├── generate_cv.py         # Resume generation utilities
├── personal_resume.yaml   # Sample resume data
├── structure.txt          # Project structure documentation
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Dependencies

- **Flask** - Web framework
- **Pydantic** - Data validation
- **LangChain** - LLM integration
- **python-docx** - Word document processing
- **PyYAML** - YAML processing
- **Werkzeug** - WSGI utilities

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license here]
