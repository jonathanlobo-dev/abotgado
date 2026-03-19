import os
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma

# 1. Configuración
DB_PATH = r"C:\Users\Jonathan Lobo\Documents\abotgado\abotgado_db"
# Pon la ruta exacta de tu carpeta de leyes si están en otra subcarpeta
NUEVOS_PDFS = [
    "codigo_penal.pdf",
    "reforma-del-codigo-penal.pdf"
]

print("Iniciando proceso de adición a la base de datos...")

embedding_function = SentenceTransformerEmbeddings(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"
)

vectorstore = Chroma(
    persist_directory=DB_PATH,
    embedding_function=embedding_function
)

nuevos_documentos = []
for archivo in NUEVOS_PDFS:
    if os.path.exists(archivo):
        print(f"📄 Leyendo: {archivo}...")
        loader = PyPDFLoader(archivo)
        docs = loader.load()
        
        # Etiquetar la ley según el nombre del archivo
        nombre_ley = "Código Penal" if "codigo" in archivo.lower() else "Reforma Código Penal"
        
        for doc in docs:
            doc.metadata["ley"] = "Código Penal" # Unificamos ambas bajo el mismo nombre para el bot
        
        nuevos_documentos.extend(docs)
    else:
        print(f"❌ Error: No se encontró el archivo {archivo}")

if nuevos_documentos:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200,
        length_function=len,
        separators=["\nArtículo", "\nCapítulo", "\nTítulo", "\n\n", "\n", " ", ""]
    )
    nuevos_fragmentos = text_splitter.split_documents(nuevos_documentos)
    
    # Extraer el número de artículo con Regex y guardarlo en el metadato
    for doc in nuevos_fragmentos:
        match = re.search(r'Artículo\s+(\d+)', doc.page_content, re.IGNORECASE)
        doc.metadata["articulo"] = int(match.group(1)) if match else 0
    
    print(f"⏳ Agregando {len(nuevos_fragmentos)} nuevos fragmentos a ChromaDB...")
    vectorstore.add_documents(nuevos_fragmentos)
    
    print("✅ ¡Leyes agregadas con éxito!")
else:
    print("⚠️ No se procesó ningún documento nuevo.")