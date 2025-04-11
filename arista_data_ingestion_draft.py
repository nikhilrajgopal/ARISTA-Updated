import os
import requests
import pdfplumber
import docx
import markdown2
import csv
import logging
logging.getLogger("pdfminer").setLevel(logging.ERROR)
import re
import json
from html.parser import HTMLParser
import chromadb
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Function to download a file from a URL
def download_file(url, save_path):
    response = requests.get(url)
    if response.status_code == 200:
        with open(save_path, 'wb') as file:
            file.write(response.content)
        return save_path
    else:
        raise Exception(f"Failed to download file from {url}. Status code: {response.status_code}")

# Function to extract text from a PDF
def extract_pdf(pdf_path):
    text_list = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_list.append(page.extract_text() or "") # Ensure no None values
    return text_list

# Function to extract text from a text file
def extract_txt(txt_path):
    with open(txt_path, 'r', encoding='utf-8') as file:
        return file.readlines()

# Function to extract text from a Word document
def extract_docx(docx_path):
    doc = docx.Document(docx_path)
    return [para.text for para in doc.paragraphs]

# Function to extract text from a Markdown file
def extract_md(md_path):
    with open(md_path, 'r', encoding='utf-8') as file:
        md_content = file.read()
    # Convert Markdown to plain text
    plain_text = markdown2.markdown(md_content) # Convert to HTML
    html_parser = HTMLParser()
    return html_parser.unescape(plain_text).splitlines() # Split by lines to simulate paragraphs

# Function to extract text from a CSV file
def extract_csv(csv_path):
    with open(csv_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
    return [' '.join(row) for row in reader] # Join each row's values into a single string

# Function to extract text from a JSON file
def extract_json(json_path):
    with open(json_path, mode='r', encoding='utf-8') as file:
        data = json.load(file)
    # If it's a nested structure, you may want to handle deeper keys depending on your needs
    return [str(data)]

# Function to extract text from an HTML file
def extract_html(html_path):
    with open(html_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
    return [HTMLParser().unescape(html_content)] # Convert HTML to plain text

# General function to extract text based on the file type
def extract(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension == ".pdf":
        return extract_pdf(file_path)
    elif file_extension == ".txt":
        return extract_txt(file_path)
    elif file_extension == ".docx":
        return extract_docx(file_path)
    elif file_extension == ".md":
        return extract_md(file_path)
    elif file_extension == ".csv":
        return extract_csv(file_path)
    elif file_extension == ".json":
        return extract_json(file_path)
    elif file_extension == ".html":
        return extract_html(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")

# Function to handle files or URLs and download if necessary
def handle_file(file_path_or_url):
    if file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://'):
        # It's a URL, download the file and process it
        temp_file_path = "temp_file" + os.path.splitext(file_path_or_url)[1].lower()
        return download_file(file_path_or_url, temp_file_path)
    else:
        # It's a local file, process it directly
        return file_path_or_url

# Function to scrape file links from a webpage
def scrape_file_links(url):
    valid_extensions = ['.pdf', '.docx', '.txt', '.csv', '.html']  # Adjust as needed

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get(url)

    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))

        file_links = [
            link.get_attribute("href")
            for link in driver.find_elements(By.TAG_NAME, "a")
            if link.get_attribute("href") and
               any(link.get_attribute("href").lower().endswith(ext) for ext in valid_extensions)
        ]

        return file_links

    except Exception as e:
        print(f"Error occurred: {e}")
        return []

    finally:
        driver.quit()

# Initialize ChromaDB
chroma_client = chromadb.PersistentClient(path="./DB")
collection = chroma_client.get_or_create_collection(
    name="multi_docs",
    metadata={"hnsw:space": "cosine"}
)

url_to_scrape = "https://www.arista.com/en/"
file_links = scrape_file_links(url_to_scrape)

def is_youtube_link(url):
    pattern = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed\/|v\/|.+\/videos\/|playlist\?list=)([a-zA-Z0-9_-]+)'
    return bool(re.match(pattern, url))

# Process the files
for file_link in file_links:
    print(file_link)
    if (not is_youtube_link(file_link)):
        try:
            # Download the file
            downloaded_file_path = handle_file(file_link)

            # Extract text from the file
            file_text = extract(downloaded_file_path)

            #Combine all page texts into one document
            full_text = "\n".join(file_text)

            # Store the full document in ChromaDB
            collection.add(
                ids=[file_link],
                documents=[full_text],
                metadatas=[{"document": file_link}]
            )
        except Exception as e:
            print(f"Error processing file {file_link}: {e}")
        
# Query the database
query = "What are Arista’s innovations in data-driven cloud networking?"
results = collection.query(
    query_texts=[query],
    n_results=3
)

# Improved result printing
print("Query Results Structure:")
print(results)

# Set your custom threshold (lower = more relevant)
relevance_threshold = 0.5

if 'documents' in results and len(results['documents'][0]) > 0:
    printed_any = False
    for i, result in enumerate(results['documents'][0]):
        distance = results['distances'][0][i] if i < len(results['distances'][0]) else None
        if distance is None or distance > relevance_threshold:
            continue  # Skip low-relevance results

        printed_any = True
        metadata = results['metadatas'][0][i] if i < len(results['metadatas'][0]) else {}
        document_num = metadata.get('document', 'N/A')
        print(f"Result {i + 1}:")
        print(f"Document: {document_num}")
        print(f"Relevance Score (distance): {distance:.2f}")
        print(f"Excerpt: {result[:300]}...\n")

    if not printed_any:
        print("No results were relevant enough (above threshold).")
else:
    print("No documents found in the results.")