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

# ==========================================
# ENVIRONMENT & CLOUD CLIENT INITIALIZATION
# ==========================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Critical Error: Missing Supabase credentials in .env file.")

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(
    title="Pocket Vogue Core AI Engine",
    description="Microservice for multimodal apparel attribute extraction and cloud persistence.",
    version="1.0.0"
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
# ALGORITHMIC SCORING HELPER FUNCTIONS
# ==========================================

def calculate_cosine_similarity(vector_a: list, vector_b: list) -> float:
    a = np.array(vector_a)
    b = np.array(vector_b)
    prod = np.dot(a, b)
    magnitude = np.linalg.norm(a) * np.linalg.norm(b)
    if magnitude == 0:
        return 0.0
    return float(prod / magnitude)


# ==========================================
# CORE API ENDPOINT
# ==========================================

@app.post("/upload-image/", summary="Process apparel image, manage storage, and persist metadata")
async def receive_image(file: UploadFile = File(...)):

    # --- Metadata extraction and safety validation ---
    filename = file.filename
    content_type = file.content_type

    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Mime-type mismatch. Uploaded file must be an image.")

    raw_img_bytes = await file.read()
    file_size = len(raw_img_bytes)

    # ==========================================
    # PHASE 1: CRYPTOGRAPHIC DE-DUPLICATION
    # ==========================================

    file_hash = hashlib.sha256(raw_img_bytes).hexdigest()

    try:
        existing_record = supabase_client.table("Items").select("*").eq("file_hash", file_hash).execute()
        if len(existing_record.data) > 0:
            return {
                "info": "Duplicate image profile identified. Bypassing execution pipeline.",
                "metadata": {
                    "name_of_file": filename,
                    "type_of_data": content_type,
                    "size_in_bytes": file_size,
                    "status": "Cache hit / Row match found"
                },
                "apparel_attributes": {
                    "clothing_type": existing_record.data[0]["clothing_type"],
                    "color": existing_record.data[0]["color"],
                    "material": existing_record.data[0]["material"],
                    "has_graphic": existing_record.data[0]["has_graphic"]
                },
                "db_record": existing_record.data[0]
            }
    except Exception as db_err:
        raise HTTPException(status_code=500, detail=f"Database verification failure: {db_err}")

    # ==========================================
    # PHASE 2: MULTIMODAL AI INFERENCE ENGINE
    # ==========================================

    virtual_file = io.BytesIO(raw_img_bytes)
    pil_image = Image.open(virtual_file)

    # --- Vector embedding extraction ---
    with torch.no_grad():
        inputs = vector_processor(images=pil_image, return_tensors="pt")
        vision_outputs = vector_model.vision_model(**inputs)
        image_features = vision_outputs.pooler_output  # actual tensor, shape [1, 768]
        # Project down to 512-d using CLIP's visual projection layer
        projected = vector_model.visual_projection(image_features)  # shape [1, 512]
        embedding_vector = F.normalize(projected, dim=-1)
        raw_embedding = embedding_vector[0].detach().numpy().flatten().tolist()

    # Guard: confirm exactly 512 dimensions before any DB write
    if len(raw_embedding) != 512:
        raise HTTPException(
            status_code=500,
            detail=f"Embedding dimension error: expected 512, got {len(raw_embedding)}"
        )

    # --- Zero-shot classification labels ---
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

    # --- Execute zero-shot classifications ---
    win_type = vision_classifier(pil_image, candidate_labels=apparel_types)[0]
    win_color = vision_classifier(pil_image, candidate_labels=apparel_colors)[0]
    win_mats = vision_classifier(pil_image, candidate_labels=apparel_materials)[0]
    win_graphics = vision_classifier(pil_image, candidate_labels=apparel_graphics)[0]

    # ==========================================
    # PHASE 3: CLOUD OBJECT STORAGE PIPELINE
    # ==========================================

    file_extension = os.path.splitext(filename)[1]
    unique_filename = f"{file_hash}{file_extension}"

    try:
        supabase_client.storage.from_("wardrobe-images").upload(
            path=unique_filename,
            file=raw_img_bytes,
            file_options={
                "content-type": content_type,
                "upsert": "true"
            }
        )
    except Exception as storage_err:
        raise HTTPException(status_code=500, detail=f"Cloud asset storage compilation error: {storage_err}")

    actual_image_url = supabase_client.storage.from_("wardrobe-images").get_public_url(unique_filename)

    # ==========================================
    # PHASE 4: RELATIONAL REGISTRY PERSISTENCE
    # ==========================================
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
        response = supabase_client.table("Items").insert(wardrobe_payload).execute()
    except Exception as ins_err:
        raise HTTPException(status_code=500, detail=f"Cloud data registry submission failure: {ins_err}")

    # ==========================================
    # RESPONSE DELIVERY
    # ==========================================

    return {
        "info": "Pipeline sequence complete. Asset hosted and metadata indexed successfully.",
        "metadata": {
            "name_of_file": filename,
            "type_of_data": content_type,
            "size_in_bytes": file_size,
            "status": "Inference and database write complete"
        },
        "apparel_attributes": {
            "clothing_type": win_type["label"],
            "color": win_color["label"],
            "material": win_mats["label"],
            "has_graphic": win_graphics["label"]
        },
        "db_record": response.data[0] if response.data else {}
    }