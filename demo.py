from langchain_groq import ChatGroq
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv
from config import system_prompt
load_dotenv()

os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.4)
loader = PyMuPDFLoader(file_path="Udit_Resume.pdf")

resume_pdf = loader.load()


prompt = ChatPromptTemplate(
    [
        ("system", system_prompt),
        ("human", "{resume}")
    ]
)

demo_chain = prompt | llm

response = demo_chain.invoke(input={"resume": resume_pdf}).content
print(response)
name = "testing"
with open(f"{name}.yaml", "w+", encoding="utf-8") as file:
    file.write(response) 
