import io
import os
import hashlib
from fastapi import FastAPI, File, UploadFile, HTTPException
from transformers import pipeline, CLIPProcessor, CLIPModel
from PIL import Image
from dotenv import load_dotenv
from supabase import create_client, Client
import numpy as np
import torch
import torch.nn.functional as F
from google import genai
import json
from pillow_heif import register_heif_opener
from typing import List


register_heif_opener()
# ==========================================
# ENVIRONMENT & CLOUD CLIENT INITIALIZATION
# ==========================================

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Critical Error: Missing Supabase credentials in .env file.")

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GOOGLE_API_KEY)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Pocket Vogue Core AI Engine",
    description="Microservice for multimodal apparel attribute extraction and cloud persistence.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    print("Initializing Foundation Vision-Language Model (CLIP)...")
    vision_classifier = pipeline(
        "zero-shot-image-classification",
        model="openai/clip-vit-base-patch32"
    )
    vector_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    vector_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    print("Model pipeline successfully loaded into memory!")
except Exception as e:
    print(f"Severe Error initializing machine learning pipeline: {e}")


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def calculate_cosine_similarity(vector_a: list, vector_b: list) -> float:
    a = np.array(vector_a)
    b = np.array(vector_b)
    prod = np.dot(a, b)
    magnitude = np.linalg.norm(a) * np.linalg.norm(b)
    if magnitude == 0:
        return 0.0
    return float(prod / magnitude)


def format_item(item):
    clothing_t = item["clothing_type"].replace("a photo of ", "")
    color = item["color"].replace(" item of clothing", "")
    material = item["material"].replace("clothing made of ", "")
    graphic = "graphic print" if item["has_graphic"] else "no graphic"
    return f"{clothing_t}, {color}, {material}, {graphic}"


# ==========================================
# UPLOAD ENDPOINT
# ==========================================

@app.post("/upload-image/")
async def receive_image(files: List[UploadFile] = File(...)):
    results = []
    
    for file in files:
        filename = file.filename
        content_type = file.content_type

        if not content_type.startswith("image/"):
            results.append({"file": filename, "error": "Not an image, skipped"})
            continue

        raw_img_bytes = await file.read()
        file_size = len(raw_img_bytes)
        file_hash = hashlib.sha256(raw_img_bytes).hexdigest()

        try:
            existing_record = supabase_client.table("Items").select("*").eq("file_hash", file_hash).execute()
            if len(existing_record.data) > 0:
                results.append({
                    "file": filename,
                    "status": "duplicate",
                    "db_record": existing_record.data[0]
                })
                continue
        except Exception as db_err:
            results.append({"file": filename, "error": f"DB check failed: {db_err}"})
            continue

        virtual_file = io.BytesIO(raw_img_bytes)
        pil_image = Image.open(virtual_file)

        with torch.no_grad():
            inputs = vector_processor(images=pil_image, return_tensors="pt")
            vision_outputs = vector_model.vision_model(**inputs)
            image_features = vision_outputs.pooler_output
            projected = vector_model.visual_projection(image_features)
            embedding_vector = F.normalize(projected, dim=-1)
            raw_embedding = embedding_vector[0].detach().numpy().flatten().tolist()

        if len(raw_embedding) != 512:
            results.append({"file": filename, "error": "Embedding dimension error"})
            continue

        apparel_types = [
            "a photo of a t-shirt or top",
            "a photo of a hoodie or sweatshirt",
            "a photo of a button-up collared shirt",
            "a photo of a sweater or knitwear",
            "a photo of a jacket or coat",
            "a photo of pants or trousers",
            "a photo of denim jeans",
            "a photo of shorts",
            "a photo of a skirt or dress",
            "a photo of shoes or sneakers"
        ]

        apparel_colors = [
            "a solid black item of clothing",
            "a pure white item of clothing",
            "a light grey or heather grey item of clothing",
            "a dark charcoal grey item of clothing",
            "a beige, tan, or khaki item of clothing",
            "a dark brown or chocolate item of clothing",
            "an olive green or army green item of clothing",
            "a rust, terracotta, or burnt orange item of clothing",
            "a navy blue or dark blue item of clothing",
            "a light blue, baby blue, or pastel blue item of clothing",
            "a bright royal blue item of clothing",
            "a faded light denim blue item of clothing",
            "a bright red item of clothing",
            "a dark red, burgundy, or maroon item of clothing",
            "a light pastel pink item of clothing",
            "a bright hot pink or fuchsia item of clothing",
            "a dark forest green item of clothing",
            "a light mint green item of clothing",
            "a bright yellow or neon yellow item of clothing",
            "a mustard yellow item of clothing",
            "a dark purple or plum item of clothing",
            "a light purple or lavender item of clothing",
            "a bright orange or peach item of clothing",
            "a multicolored, patterned, or printed item of clothing",
            "a metallic silver or gold item of clothing"
        ]

        apparel_materials = [
            "clothing made of soft cotton fabric",
            "clothing made of blue or black denim fabric",
            "clothing made of genuine leather or suede",
            "clothing made of heavy wool or thick knitwear",
            "clothing made of smooth synthetic athletic material",
            "clothing made of lightweight linen or silk fabric"
        ]

        apparel_graphics = [
            "plain solid clothing with no graphics, logos, or prints",
            "graphic clothing featuring a prominent print, illustration, text, or logo design"
        ]

        win_type = vision_classifier(pil_image, candidate_labels=apparel_types)[0]
        win_color = vision_classifier(pil_image, candidate_labels=apparel_colors)[0]
        win_mats = vision_classifier(pil_image, candidate_labels=apparel_materials)[0]
        win_graphics = vision_classifier(pil_image, candidate_labels=apparel_graphics)[0]

        # Convert HEIC/HEIF images to JPEG so browsers can display them
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension in (".heic", ".heif"):
            jpeg_buffer = io.BytesIO()
            pil_image.convert("RGB").save(jpeg_buffer, format="JPEG", quality=90)
            upload_bytes = jpeg_buffer.getvalue()
            unique_filename = f"{file_hash}.jpg"
            upload_content_type = "image/jpeg"
        else:
            upload_bytes = raw_img_bytes
            unique_filename = f"{file_hash}{file_extension}"
            upload_content_type = content_type

        try:
            supabase_client.storage.from_("wardrobe-images").upload(
                path=unique_filename,
                file=upload_bytes,
                file_options={"content-type": upload_content_type, "upsert": "true"}
            )
        except Exception as storage_err:
            results.append({"file": filename, "error": f"Storage failed: {storage_err}"})
            continue

        actual_image_url = supabase_client.storage.from_("wardrobe-images").get_public_url(unique_filename)
        has_graphic_bool = win_graphics["label"] == "graphic clothing featuring a prominent print, illustration, text, or logo design"

        wardrobe_payload = {
            "image_url": actual_image_url,
            "file_hash": file_hash,
            "clothing_type": win_type["label"],
            "color": win_color["label"],
            "material": win_mats["label"],
            "has_graphic": has_graphic_bool,
            "embedding": raw_embedding
        }

        try:
            upload_response = supabase_client.table("Items").insert(wardrobe_payload).execute()
        except Exception as ins_err:
            results.append({"file": filename, "error": f"DB insert failed: {ins_err}"})
            continue

        results.append({
            "file": filename,
            "status": "success",
            "apparel_attributes": {
                "clothing_type": win_type["label"],
                "color": win_color["label"],
                "material": win_mats["label"],
                "has_graphic": has_graphic_bool
            },
            "db_record": upload_response.data[0] if upload_response.data else {}
        })

    return {"uploaded": results}

# ==========================================
# OUTFIT GENERATION ENDPOINT
# ==========================================

@app.get("/generate-outfit/{item_id}")
async def generate_outfit(item_id: int):

    # Step 1: fetch embedding
    result = supabase_client.table("Items").select("*").eq("id", item_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    query_embedding = result.data[0]["embedding"]

    # Supabase returns the embedding as a JSON string — parse it back to a list
    if isinstance(query_embedding, str):
        query_embedding = json.loads(query_embedding)

    # Step 2: similarity search (computed in-app since pgvector RPC may not exist)
    all_items = supabase_client.table("Items").select("*").neq("id", item_id).execute()

    query_vec = np.array(query_embedding)
    scored_items = []
    for item in all_items.data:
        emb = item["embedding"]
        if isinstance(emb, str):
            emb = json.loads(emb)
        item_vec = np.array(emb)
        similarity = float(np.dot(query_vec, item_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(item_vec) + 1e-9))
        scored_items.append((similarity, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    matched_items = [item for _, item in scored_items[:5]]

    # Step 3: build prompt
    query_item = format_item(result.data[0])
    candidates = "\n".join(
        f"{i+1}. (id={item['id']}) {format_item(item)}"
        for i, item in enumerate(matched_items)
    )

    prompt = f"""
        You are a professional fashion stylist.

        You are building an outfit around this base item:
        {query_item}

        Here are candidate items from the user's wardrobe:
        {candidates}

        Select items that work together as a complete outfit with the base item.
        Not every candidate needs to be included.

        Return your response in this exact JSON format:
        {{
            "outfit": [
                {{"id": ..., "item": "...", "reason": "..."}}
            ],
            "overall_description": "..."
        }}
        """

    # Step 4: call Gemini
    try:
        gemini_response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
    except Exception as gemini_err:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Gemini API error: {str(gemini_err)}")
    # Step 5: strip markdown and parse JSON
    try:
        raw = gemini_response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        outfit = json.loads(raw)
    except (json.JSONDecodeError, AttributeError) as parse_err:
        raise HTTPException(status_code=500, detail=f"Failed to parse Gemini response: {parse_err}")

    return outfit

@app.get("/wardrobe/")
async def get_wardrobe():
    try:
        result = supabase_client.table("Items").select("*").execute()
        return {"items": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch wardrobe: {e}")