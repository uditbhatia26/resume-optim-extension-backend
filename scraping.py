from flask import Flask, request, jsonify
from pydantic import Field, BaseModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

app = Flask(__name__)
load_dotenv()

# Define structured output schema
class ScraperModel(BaseModel):
    job_description: str = Field(description="Extracted job description")
    skills: list[str] = Field(description="Skills extracted for the job")

# Load API keys from .env
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
os.environ["LANGSMITH_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ["LANGSMITH_TRACING"] = os.getenv("LANGSMITH_TRACING")
os.environ["LANGSMITH_PROJECT"] = os.getenv("LANGSMITH_PROJECT")

# Home route
@app.route("/")
def home():
    return "Hello, Flask is running!"


@app.route("/api/job-description", methods=["POST"])
def extract_job_description():
    """
    Function to extract job description and skills required from a webpage

    Returns:
        job_description (str): The extracted job description
        skills_required (list(str)): The extracted skills 
    """
    data = request.get_json()
    url = data.get("url")
    
    if not url:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    try:
        loader = WebBaseLoader(url)
        docs = loader.load()
    except Exception as e:
        return jsonify({"error": f"Failed to load content from URL: {str(e)}"}), 500

    extraction_system_prompt = """
        You are a job listing parser. Carefully extract the **entire job description**. 
        Also extract the **required skills** explicitly mentioned in the text.
    """
    jd_extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", extraction_system_prompt),
        ("human", "{docs}")
    ])

    llm = ChatGroq(model="llama-3.3-70b-versatile") 
    jd_extraction_chain = jd_extraction_prompt | llm.with_structured_output(ScraperModel)

    try:
        response = jd_extraction_chain.invoke({"docs": docs[0].page_content})
        return jsonify({
            "job_description": response.job_description,
            "skills": response.skills
        })
    except Exception as e:
        return jsonify({"error": f"LLM parsing failed: {str(e)}"}), 500


# Run Flask app
if __name__ == "__main__":
    app.run(debug=True)
