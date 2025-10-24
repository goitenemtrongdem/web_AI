# app/api/v1/inspections_api.py
# -*- coding: utf-8 -*-

"""
Inspections API - Upload ZIP (stream), quản lý ảnh, chạy AI từng ảnh, và trả JSON results cho FE vẽ bbox.
Flow:
1) POST /inspections/turbine/{turbine_id}/upload      -> tạo inspection + lưu ảnh (KHÔNG chạy AI). TRẢ VỀ: inspection_id,...
2) GET  /inspections/turbine/{turbine_id}             -> danh sách inspections
3) GET  /inspections/{inspection_id}                  -> chi tiết inspection (raw URLs), CHƯA dính bbox
4) POST /inspections/images/{image_id}/analyze        -> phân tích AI CHO 1 ẢNH, tạo/ghi damage_assessments
5) GET  /inspections/{inspection_id}/results          -> JSON cho FE vẽ bbox
6) DELETE /inspections/{inspection_id}/images         -> xóa nhiều ảnh khỏi 1 inspection
7) PATCH  /inspections/{inspection_id}                -> cập nhật metadata inspection
8) PATCH  /inspections/images/{image_id}/assessment   -> cập nhật assessment (manual override)
"""

import os
import uuid
import shutil
import zipfile
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
load_dotenv()

from ultralytics import YOLO
import torch

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.database import (
    database,
    inspections_table,
    inspection_images_table,
    damage_assessments_table,
    turbines_table,
    users_table,
    windfarms_table,
)
from app.db.models import InspectionStatus, ImageStatus
from app.utilities.permissions import check_turbine_access
from app.api.v1.users_admin.auth_routes import require_user
from app.core.config import get_inspection_storage_path, TEMP_UPLOAD_DIR


router = APIRouter(prefix="/inspections", tags=["inspections"])


# =========================
# Request Models
# =========================

class DeleteImagesRequest(BaseModel):
    image_ids: List[str]

class UpdateInspectionRequest(BaseModel):
    operator: Optional[str] = None
    equipment: Optional[str] = None
    status: Optional[str] = None
    captured_at: Optional[datetime] = None

class UpdateAssessmentRequest(BaseModel):
    """✅ Request body cho UPDATE damage assessment (description + ai_bounding_boxes)"""
    description: Optional[str] = None  # User notes
    ai_bounding_boxes: Optional[List[Dict[str, Any]]] = None  # Allow editing AI bounding boxes (including type/LV)

class PartialUpdateBoxRequest(BaseModel):
    """✅ Request body cho UPDATE từng bounding box (partial update by index)"""
    box_index: int = Field(..., ge=0, description="Index của box cần sửa (bắt đầu từ 0)")
    updates: Dict[str, Any] = Field(..., description="Các field cần update (type, confidence, x, y, width, height)")


# =========================
# Helpers / Service
# =========================

class _Service:
    # Cho phép tuỳ chỉnh theo chuẩn của bạn
    VALID_BLADES = ["BladeA", "BladeB", "BladeC"]
    VALID_SURFACES = ["PS", "LE", "TE", "SS"]
    VALID_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp"]
    MAX_ZIP_SIZE = 500 * 1024 * 1024  # 500MB

    def __init__(self):
        # ⚡ Load YOLOv8 model 1 lần khi service khởi tạo
        model_path = os.getenv("AI_MODEL_PATH", "models/blade_yolov8.pt")
        print(f"🤖 Loading YOLO model from: {model_path}")
        
        if not os.path.exists(model_path):
            raise RuntimeError(f"⚠️ Không tìm thấy model YOLOv8 tại: {model_path}")
        
        self.model = YOLO(model_path)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"✅ Model loaded successfully!")
        print(f"📊 Device: {self.device}")
        print(f"🏷️  Model classes: {self.model.names}")

    # ---------- Basic DB getters ----------

    async def get_turbine_full(self, turbine_id: str) -> Optional[Dict[str, Any]]:
        q_t = sa.select(
            turbines_table.c.id,
            turbines_table.c.name,
            turbines_table.c.windfarm_id,
        ).where(turbines_table.c.id == turbine_id)
        t = await database.fetch_one(q_t)
        if not t:
            return None
        q_w = sa.select(windfarms_table.c.project_id).where(windfarms_table.c.id == t["windfarm_id"])
        w = await database.fetch_one(q_w)
        return {
            "id": str(t["id"]),
            "name": t["name"],
            "windfarm_id": str(t["windfarm_id"]),
            "project_id": str(w["project_id"]) if w else None,
        }

    async def get_user_min(self, user_id: str) -> Dict[str, Any]:
        q = sa.select(users_table.c.id, users_table.c.name, users_table.c.email).where(users_table.c.id == user_id)
        r = await database.fetch_one(q)
        if r:
            return {"id": str(r["id"]), "name": r["name"], "email": r["email"]}
        return {"id": str(user_id), "name": "Unknown User", "email": "unknown@example.com"}

    # ---------- ZIP parsing & saving ----------

    def _parse_zip(self, extract_dir: Path) -> List[Dict[str, Any]]:
        """
        Quét thư mục đã giải nén. Yêu cầu: BladeX/<surface>/*.jpg (hoặc .jpeg/.png/.bmp)
        Cho phép có 1 root folder bọc ngoài.
        Trả về: [{ blade, surface, filename, temp_path, position_pct }]
        """
        files: List[Dict[str, Any]] = []
        search_dirs = [extract_dir]
        subs = [d for d in extract_dir.iterdir() if d.is_dir()]
        if len(subs) == 1:
            search_dirs.append(subs[0])

        for root in search_dirs:
            for blade in self.VALID_BLADES:
                bdir = root / blade
                if not bdir.exists():
                    continue
                for surf in self.VALID_SURFACES:
                    sdir = bdir / surf
                    if not sdir.exists():
                        continue
                    for p in sdir.iterdir():
                        if p.is_file() and p.suffix.lower() in self.VALID_IMAGE_EXTENSIONS:
                            files.append({
                                "blade": blade,
                                "surface": surf,
                                "filename": p.name,
                                "temp_path": p,
                                "position_pct": self._extract_position_pct(p.name)
                            })
            if files:
                break
        return files

    def _extract_position_pct(self, name: str) -> Optional[float]:
        """Ví dụ: IMG_0082_D.JPG -> 82; nếu không trích xuất được thì None."""
        try:
            stem = Path(name).stem
            parts = stem.split("_")
            for part in reversed(parts):
                if part.isdigit():
                    return float(part)
        except:
            pass
        return None

    # ---------- Inspection creation (from ZIP path) ----------

    async def create_inspection_from_zip_path(
        self,
        turbine_id: str,
        zip_path: str,
        user_id: str,
        operator: Optional[str],
        equipment: Optional[str],
        captured_at: Optional[datetime],
    ) -> Dict[str, Any]:
        """Tạo inspection và lưu ảnh từ đường dẫn file ZIP (đã lưu tạm)."""
        turbine = await self.get_turbine_full(turbine_id)
        if not turbine:
            raise HTTPException(status_code=404, detail="Turbine không tồn tại")

        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(status_code=400, detail="📦 File không phải ZIP hợp lệ")

        extract_dir = Path(TEMP_UPLOAD_DIR) / f"extract_{uuid.uuid4()}"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            imgs = self._parse_zip(extract_dir)
            if not imgs:
                raise HTTPException(status_code=400, detail="ZIP không hợp lệ. Cần cấu trúc: BladeA/PS/*.jpg")

            # create inspection
            inspection_id = str(uuid.uuid4())
            code = f"INSP-{datetime.now().strftime('%Y%m%d')}-{inspection_id[:8]}"

            paths = get_inspection_storage_path(
                project_id=turbine["project_id"],
                windfarm_id=turbine["windfarm_id"],
                turbine_id=turbine_id,
                inspection_id=inspection_id,
            )
            base_path = Path(paths["base_path"])
            raw_root = Path(paths["raw_images_path"])
            raw_root.mkdir(parents=True, exist_ok=True)

            data_ins = {
                "id": inspection_id,
                "turbine_id": turbine_id,
                "inspection_code": code,
                "status": InspectionStatus.UPLOADED.value,
                "captured_at": captured_at or datetime.now(),
                "operator": operator,
                "equipment": equipment,
                "storage_path": str(base_path),
                "total_images": len(imgs),
                "processed_images": 0,
                "created_by": user_id,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            await database.execute(inspections_table.insert().values(data_ins))

            # copy images -> DB rows
            for it in imgs:
                dest_dir = raw_root / it["blade"] / it["surface"]
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / it["filename"]
                shutil.copy2(it["temp_path"], dest_path)

                image_id = str(uuid.uuid4())
                row = {
                    "id": image_id,
                    "inspection_id": inspection_id,
                    "blade": it["blade"],
                    "surface": it["surface"],
                    "position_pct": it.get("position_pct"),
                    "position_meter": None,
                    "file_name": it["filename"],
                    "file_path": str(dest_path),
                    "file_size": os.path.getsize(dest_path),
                    "captured_at": captured_at or datetime.now(),
                    "status": ImageStatus.UPLOADED.value,
                    "checked_flag": "Unchecked",
                    "created_at": datetime.now(),
                }
                await database.execute(inspection_images_table.insert().values(row))

            return {
                "inspection_id": inspection_id,
                "turbine_id": turbine_id,
                "inspection_code": code,
                "status": "uploaded",
                "total_images": len(imgs),
                "created_at": data_ins["created_at"].isoformat(),
            }

        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
            try:
                os.remove(zip_path)
            except:
                pass

    # ---------- Queries for FE ----------

    async def list_inspections(self, turbine_id: str, status_filter: Optional[str], limit: int, offset: int):
        q = sa.select(inspections_table).where(inspections_table.c.turbine_id == turbine_id)
        if status_filter:
            q = q.where(inspections_table.c.status == status_filter)
        q = q.order_by(inspections_table.c.created_at.desc())
        q = q.limit(limit).offset(offset)
        rows = await database.fetch_all(q)
        res: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            for k in ("id", "turbine_id", "created_by"):
                if k in d and d[k] is not None:
                    d[k] = str(d[k])
            if "status" in d and hasattr(d["status"], "value"):
                d["status"] = d["status"].value
            res.append(d)
        return res

    async def get_inspection(self, inspection_id: str) -> Optional[Dict[str, Any]]:
        r = await database.fetch_one(sa.select(inspections_table).where(inspections_table.c.id == inspection_id))
        if not r:
            return None
        d = dict(r)
        d["id"] = str(d["id"])
        d["turbine_id"] = str(d["turbine_id"])
        if d.get("created_by"):
            d["created_by"] = str(d["created_by"])
        return d

    async def get_images_for_inspection(self, inspection_id: str) -> List[Dict[str, Any]]:
        q = (
            sa.select(inspection_images_table)
            .where(inspection_images_table.c.inspection_id == inspection_id)
            .order_by(
                inspection_images_table.c.blade,
                inspection_images_table.c.surface,
                inspection_images_table.c.position_pct,
            )
        )
        rows = await database.fetch_all(q)
        images: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["id"] = str(d["id"])
            d["inspection_id"] = str(d["inspection_id"])
            d["image_id"] = d["id"]
            d["file_url"] = f"/api/v1/inspections/images/{d['id']}/stream"
            d["processed_url"] = f"/api/v1/inspections/images/{d['id']}/processed"
            d["checkedFlag"] = d.get("checked_flag", "Unchecked")
            images.append(d)
        return images

    async def get_image(self, image_id: str) -> Optional[Dict[str, Any]]:
        r = await database.fetch_one(sa.select(inspection_images_table).where(inspection_images_table.c.id == image_id))
        return dict(r) if r else None

    async def get_turbine_id_from_image(self, image_id: str) -> Optional[str]:
        q = sa.select(inspections_table.c.turbine_id).select_from(
            inspection_images_table.join(inspections_table, inspection_images_table.c.inspection_id == inspections_table.c.id)
        ).where(inspection_images_table.c.id == image_id)
        r = await database.fetch_one(q)
        return str(r["turbine_id"]) if r else None

    async def update_assessment(self, image_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """✅ Cập nhật damage assessment - description + ai_bounding_boxes (cho phép sửa LV level)"""
        # Get assessment
        assessment = await database.fetch_one(
            sa.select(damage_assessments_table)
            .where(damage_assessments_table.c.inspection_image_id == image_id)
        )
        if not assessment:
            raise HTTPException(status_code=404, detail="Không tìm thấy damage assessment cho image này")
        
        # Allow updating description and ai_bounding_boxes
        update_data = {}
        if "description" in updates:
            update_data["description"] = updates["description"]
        
        if "ai_bounding_boxes" in updates:
            # Validate bounding boxes structure
            bboxes = updates["ai_bounding_boxes"]
            if bboxes is not None:
                if not isinstance(bboxes, list):
                    raise HTTPException(status_code=400, detail="ai_bounding_boxes phải là array")
                
                # Validate each bounding box
                for bbox in bboxes:
                    required_fields = ["x", "y", "width", "height", "type", "confidence"]
                    for field in required_fields:
                        if field not in bbox:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Bounding box thiếu field '{field}'"
                            )
            
            update_data["ai_bounding_boxes"] = bboxes
        
        if not update_data:
            raise HTTPException(status_code=400, detail="Không có trường hợp lệ để cập nhật")
        
        update_data["updated_at"] = datetime.now()
        
        # Execute update
        await database.execute(
            damage_assessments_table.update()
            .where(damage_assessments_table.c.id == assessment["id"])
            .values(update_data)
        )
        
        # Return updated assessment
        updated = await database.fetch_one(
            sa.select(damage_assessments_table)
            .where(damage_assessments_table.c.id == assessment["id"])
        )
        
        return {
            "message": "Cập nhật damage assessment thành công",
            "assessment": {
                "id": str(updated["id"]),
                "image_id": str(image_id),
                "ai_bounding_boxes": updated["ai_bounding_boxes"],
                "description": updated["description"],
                "updated_at": updated["updated_at"].isoformat() if updated["updated_at"] else None,
            }
        }

    async def partial_update_bounding_box(self, image_id: str, box_index: int, field_updates: Dict[str, Any]) -> Dict[str, Any]:
        """✅ Cập nhật một hoặc nhiều field của 1 bounding box cụ thể (partial update by index)"""
        # Get assessment
        assessment = await database.fetch_one(
            sa.select(damage_assessments_table)
            .where(damage_assessments_table.c.inspection_image_id == image_id)
        )
        if not assessment:
            raise HTTPException(status_code=404, detail="Không tìm thấy damage assessment cho image này")
        
        # Get current bounding boxes
        current_boxes = assessment["ai_bounding_boxes"] or []
        if not current_boxes:
            raise HTTPException(status_code=400, detail="Không có bounding box nào để cập nhật")
        
        if box_index < 0 or box_index >= len(current_boxes):
            raise HTTPException(
                status_code=400, 
                detail=f"box_index={box_index} không hợp lệ. Chỉ có {len(current_boxes)} boxes (index từ 0-{len(current_boxes)-1})"
            )
        
        # Validate và merge updates vào box hiện tại
        allowed_fields = ["x", "y", "width", "height", "type", "confidence"]
        for field in field_updates:
            if field not in allowed_fields:
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field}' không được phép. Chỉ cho phép: {allowed_fields}"
                )
        
        # Update specific box
        updated_box = {**current_boxes[box_index], **field_updates}
        current_boxes[box_index] = updated_box
        
        # Save back to database
        await database.execute(
            damage_assessments_table.update()
            .where(damage_assessments_table.c.id == assessment["id"])
            .values({
                "ai_bounding_boxes": current_boxes,
                "updated_at": datetime.now()
            })
        )
        
        # Return updated assessment
        updated = await database.fetch_one(
            sa.select(damage_assessments_table)
            .where(damage_assessments_table.c.id == assessment["id"])
        )
        
        return {
            "message": f"Cập nhật box index {box_index} thành công",
            "assessment": {
                "id": str(updated["id"]),
                "image_id": str(image_id),
                "ai_bounding_boxes": updated["ai_bounding_boxes"],
                "updated_box_index": box_index,
                "updated_box": updated_box,
                "description": updated["description"],
                "updated_at": updated["updated_at"].isoformat() if updated["updated_at"] else None,
            }
        }

    # ---------- AI per-image ----------

    async def analyze_one_image(self, image_id: str) -> Dict[str, Any]:
        img = await self.get_image(image_id)
        if not img:
            raise HTTPException(status_code=404, detail="Image không tồn tại")

        await database.execute(
            inspection_images_table.update()
            .where(inspection_images_table.c.id == image_id)
            .values({"status": ImageStatus.PROCESSING.value})
        )

        detection_result = await self._yolov8_detect(img["file_path"])
        if not detection_result:
            await database.execute(
                inspection_images_table.update()
                .where(inspection_images_table.c.id == image_id)
                .values({"status": ImageStatus.FAILED.value})
            )
            return {"image_id": str(image_id), "status": "failed"}

        existing = await database.fetch_one(
            sa.select(
                damage_assessments_table.c.id,
                damage_assessments_table.c.description,
            ).where(damage_assessments_table.c.inspection_image_id == image_id)
        )

        # ✅ Chỉ lưu data AI thuần túy; description được giữ lại khi re-analyze
        user_description: Optional[str] = existing["description"] if existing else None
        data_ass = {
            "ai_bounding_boxes": detection_result.get("bounding_boxes", []),
            "ai_processed_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        if existing:
            await database.execute(
                damage_assessments_table.update()
                .where(damage_assessments_table.c.id == existing["id"])
                .values(data_ass)
            )
            ass_id = str(existing["id"])
        else:
            ass_id = str(uuid.uuid4())
            await database.execute(
                damage_assessments_table.insert().values(
                    {
                        "id": ass_id,
                        "inspection_image_id": image_id,
                        **data_ass,
                        "created_at": datetime.now(),
                    }
                )
            )

        await database.execute(
            inspection_images_table.update()
            .where(inspection_images_table.c.id == image_id)
            .values({"status": ImageStatus.ANALYZED.value, "checked_flag": "Processed"})
        )

        await database.execute(
            inspections_table.update()
            .where(inspections_table.c.id == img["inspection_id"])
            .values({
                "processed_images": sa.literal_column("processed_images") + 1,
                "status": InspectionStatus.PROCESSING.value,
                "updated_at": datetime.now()
            })
        )

        # ✅ Simplified response: Pure AI data + description field
        return {
            "image_id": str(image_id),
            "status": "analyzed",
            "assessment_id": ass_id,
            "damage_assessments": [
                {
                    "ai_bounding_boxes": data_ass["ai_bounding_boxes"],
                    "description": user_description,  # User notes (default None)
                }
            ],
        }

    async def _yolov8_detect(self, image_path: str) -> Dict[str, Any]:
        """
        Chạy YOLOv8 để phát hiện hư hại trên ảnh turbine blade.
        Trả về bounding_boxes array - mỗi box chứa đầy đủ thông tin: x, y, width, height, type, confidence
        """
        print(f"🔍 Analyzing image: {image_path}")
        print(f"📊 Model device: {self.device}")
        
        results = self.model.predict(
            source=image_path,
            imgsz=1024,
            conf=0.35,  # ⚡ Lowered confidence threshold from 0.3 to 0.1
            device=self.device,
            verbose=False,
        )
        result = results[0]
        
        print(f"📦 Total detections: {len(result.boxes)}")
        
        boxes: List[Dict[str, Any]] = []

        for box in result.boxes:
            # an toàn với tensor shape (N,1)
            cls_id = int(box.cls[0])
            cls_name = result.names[cls_id]
            conf = float(box.conf[0])

            x_center, y_center, w, h = box.xywhn[0].tolist()
            boxes.append({
                "x": round(float(x_center), 4),
                "y": round(float(y_center), 4),
                "width": round(float(w), 4),
                "height": round(float(h), 4),
                "type": cls_name,        # FE sẽ đọc LV_X từ đây
                "confidence": conf,
            })
            print(f"✅ Detected: {cls_name} (conf: {conf:.3f})")

        final_result = {
            "bounding_boxes": boxes,
        }
        
        print(f"🎯 Final result: {len(boxes)} damages detected")
        return final_result

    # ---------- Results JSON ----------

    async def build_results_json(self, inspection_id: str) -> Dict[str, Any]:
        ins = await self.get_inspection(inspection_id)
        if not ins:
            raise HTTPException(status_code=404, detail="Inspection không tồn tại")

        images = await self.get_images_for_inspection(inspection_id)
        out_images: List[Dict[str, Any]] = []

        for img in images:
            rows = await database.fetch_all(
                sa.select(damage_assessments_table)
                .where(damage_assessments_table.c.inspection_image_id == img["id"])
                .order_by(damage_assessments_table.c.ai_processed_at.desc().nullslast())
            )

            # ✅ Ultra-simplified assessments: only bounding boxes (contains all info) + description
            assessments = []
            for r in rows:
                d = dict(r)
                # 🎯 Each bounding box already contains: x, y, width, height, type, confidence
                assessments.append({
                    "ai_bounding_boxes": d.get("ai_bounding_boxes") or [],
                    "description": d.get("description"),
                })

            out_images.append({
                "image_id": img["id"],
                "blade": img["blade"],
                "surface": img["surface"],
                "file_name": img["file_name"],
                "status": img.get("status"),
                "file_url": img["file_url"],
                "assessments": assessments,
            })

        # Thống kê gọn
        stats = {
            "total_images": len(out_images),
            "analyzed_images": sum(1 for i in images if (i.get("status") == ImageStatus.ANALYZED.value)),
        }

        # Metadata gọn
        metadata = {
            "inspection_id": ins["id"],
            "inspection_code": ins["inspection_code"],
            "status": ins["status"],
            "total_images": ins.get("total_images"),
            "processed_images": ins.get("processed_images"),
        }

        return {
            "metadata": metadata,
            "statistics": stats,
            "images": out_images,
        }

    # ---------- Extra CRUD ----------

    async def delete_images(self, inspection_id: str, image_ids: List[str]) -> Dict[str, Any]:
        # Xóa rows + assessment; không xóa file disk để an toàn (muốn xóa file disk thì thêm os.remove)
        deleted_ids = []
        for img_id in image_ids:
            img = await database.fetch_one(sa.select(inspection_images_table).where(inspection_images_table.c.id == img_id))
            if img and str(img["inspection_id"]) == inspection_id:
                # Optionally xóa file trên disk (bật nếu cần)
                # try:
                #     p = Path(img["file_path"])
                #     if p.exists():
                #         p.unlink()
                # except:
                #     pass

                await database.execute(
                    damage_assessments_table.delete().where(damage_assessments_table.c.inspection_image_id == img_id)
                )
                await database.execute(
                    inspection_images_table.delete().where(inspection_images_table.c.id == img_id)
                )
                deleted_ids.append(img_id)

        remaining = await database.fetch_val(
            sa.select(sa.func.count()).select_from(inspection_images_table).where(inspection_images_table.c.inspection_id == inspection_id)
        )

        # Cập nhật total_images trong inspections_table cho khớp
        await database.execute(
            inspections_table.update()
            .where(inspections_table.c.id == inspection_id)
            .values({"total_images": int(remaining), "updated_at": datetime.now()})
        )

        return {
            "message": f"Đã xóa {len(deleted_ids)} ảnh",
            "inspection_id": inspection_id,
            "deleted_count": len(deleted_ids),
            "deleted_ids": deleted_ids,
            "remaining_images": int(remaining),
        }

    async def update_inspection(self, inspection_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        updates = {k: v for k, v in updates.items() if v is not None}
        updates["updated_at"] = datetime.now()

        await database.execute(
            inspections_table.update()
            .where(inspections_table.c.id == inspection_id)
            .values(updates)
        )
        updated = await database.fetch_one(sa.select(inspections_table).where(inspections_table.c.id == inspection_id))
        return {"message": "Cập nhật inspection thành công", "inspection": dict(updated)}


_service = _Service()


# =========================
# Routes
# =========================

@router.post("/turbine/{turbine_id}/upload", status_code=status.HTTP_201_CREATED)
async def upload_inspection(
    turbine_id: str,
    file: UploadFile = File(...),
    operator: Optional[str] = None,
    equipment: Optional[str] = None,
    captured_at: Optional[datetime] = None,
    current_user: dict = Depends(require_user),
):
    """
    1) Upload ZIP -> tạo inspection + lưu ảnh (stream, không đọc hết vào RAM).
    - Không ép tên file .zip; kiểm tra định dạng bằng nội dung.
    - Giới hạn kích thước theo MAX_ZIP_SIZE.
    """
    await check_turbine_access(turbine_id, current_user, min_role="editor")

    # Lưu về file tạm theo streaming + enforce MAX_ZIP_SIZE
    tmp_dir = Path(TEMP_UPLOAD_DIR)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_zip = tmp_dir / f"{uuid.uuid4()}.zip"

    bytes_written = 0
    CHUNK = 1024 * 1024  # 1MB

    with open(tmp_zip, "wb") as f:
        while True:
            chunk = await file.read(CHUNK)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > _Service.MAX_ZIP_SIZE:
                try:
                    f.close()
                except:
                    pass
                try:
                    tmp_zip.unlink(missing_ok=True)
                except:
                    pass
                raise HTTPException(status_code=400, detail=f"ZIP quá lớn (> {_Service.MAX_ZIP_SIZE // 1024 // 1024}MB)")
            f.write(chunk)

    # Kiểm tra chính xác ZIP
    if not zipfile.is_zipfile(tmp_zip):
        try:
            tmp_zip.unlink(missing_ok=True)
        except:
            pass
        raise HTTPException(status_code=400, detail="📦 File không phải định dạng ZIP hợp lệ")

    # Tạo inspection từ path
    result = await _service.create_inspection_from_zip_path(
        turbine_id=turbine_id,
        zip_path=str(tmp_zip),
        user_id=current_user["id"],
        operator=operator,
        equipment=equipment,
        captured_at=captured_at,
    )
    return result


@router.get("/turbine/{turbine_id}")
async def list_inspections(
    turbine_id: str,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(require_user),
):
    await check_turbine_access(turbine_id, current_user, min_role="viewer")
    return await _service.list_inspections(turbine_id, status_filter, limit, offset)


@router.get("/{inspection_id}")
async def get_inspection_detail(
    inspection_id: str,
    current_user: dict = Depends(require_user),
):
    ins = await _service.get_inspection(inspection_id)
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection không tồn tại")
    await check_turbine_access(ins["turbine_id"], current_user, min_role="viewer")
    images = await _service.get_images_for_inspection(inspection_id)
    return {
        "inspection": ins,
        "total_images": len(images),
        "images": images,
    }


@router.post("/images/{image_id}/analyze")
async def analyze_one_image(
    image_id: str,
    current_user: dict = Depends(require_user),
):
    turbine_id = await _service.get_turbine_id_from_image(image_id)
    if not turbine_id:
        raise HTTPException(status_code=404, detail="Image không tồn tại")
    await check_turbine_access(turbine_id, current_user, min_role="editor")

    return await _service.analyze_one_image(image_id)


@router.get("/{inspection_id}/results")
async def get_results(
    inspection_id: str,
    current_user: dict = Depends(require_user),
):
    ins = await _service.get_inspection(inspection_id)
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection không tồn tại")
    await check_turbine_access(ins["turbine_id"], current_user, min_role="viewer")
    return await _service.build_results_json(inspection_id)


@router.delete("/{inspection_id}/images", status_code=status.HTTP_200_OK)
async def delete_inspection_images(
    inspection_id: str,
    request: DeleteImagesRequest,
    current_user: dict = Depends(require_user),
):
    """
    Xóa nhiều ảnh khỏi inspection.
    Body: {"image_ids": ["uuid1","uuid2",...]}
    """
    ins = await _service.get_inspection(inspection_id)
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection không tồn tại")

    await check_turbine_access(ins["turbine_id"], current_user, min_role="editor")
    return await _service.delete_images(inspection_id, request.image_ids)


@router.patch("/{inspection_id}", status_code=status.HTTP_200_OK)
async def update_inspection(
    inspection_id: str,
    request: UpdateInspectionRequest,
    current_user: dict = Depends(require_user),
):
    """
    Cập nhật thông tin inspection (operator, equipment, status, captured_at)
    """
    ins = await _service.get_inspection(inspection_id)
    if not ins:
        raise HTTPException(status_code=404, detail="Inspection không tồn tại")

    await check_turbine_access(ins["turbine_id"], current_user, min_role="editor")
    return await _service.update_inspection(inspection_id, request.dict(exclude_unset=True))


@router.patch("/images/{image_id}/assessment", status_code=status.HTTP_200_OK)
async def update_image_assessment(
    image_id: str,
    request: UpdateAssessmentRequest,
    current_user: dict = Depends(require_user),
):
    """
    ✅ Cập nhật damage assessment cho image (description + bounding boxes).
    
    **Use Cases:**
    - Thêm/sửa ghi chú manual cho damage
    - Chỉnh sửa LV level (type) của AI detection
    - Thêm/xóa/sửa bounding boxes
    
    **Request Body Examples:**
    
    1. **Chỉ sửa description:**
    ```json
    {
      "description": "Vết nứt chạy dọc, cần theo dõi thêm"
    }
    ```
    
    2. **Chỉ sửa LV level (type) trong bounding box:**
    ```json
    {
      "ai_bounding_boxes": [
        {
          "x": 0.6258,
          "y": 0.3321,
          "width": 0.6403,
          "height": 0.6395,
          "type": "LV_5",
          "confidence": 0.78
        }
      ]
    }
    ```
    
    3. **Sửa cả description và bounding boxes:**
    ```json
    {
      "description": "Đã review lại, nâng cấp độ lên LV_5",
      "ai_bounding_boxes": [
        {
          "x": 0.6258,
          "y": 0.3321,
          "width": 0.6403,
          "height": 0.6395,
          "type": "LV_5",
          "confidence": 0.78
        }
      ]
    }
    ```
    
    **Allowed fields:**
    - description (string, optional): Ghi chú của người kiểm tra
    - ai_bounding_boxes (array, optional): Danh sách bounding boxes (có thể sửa type/LV)
      - Each box requires: x, y, width, height, type, confidence
    
    **Returns:**
    ```json
    {
      "message": "Cập nhật damage assessment thành công",
      "assessment": {
        "id": "assessment-uuid",
        "image_id": "image-uuid",
        "ai_bounding_boxes": [
          {"x": 0.6258, "y": 0.3321, "width": 0.6403, "height": 0.6395, "type": "LV_5", "confidence": 0.78}
        ],
        "description": "Đã review lại, nâng cấp độ lên LV_5",
        "updated_at": "2025-10-23T08:35:00Z"
      }
    }
    ```
    
    **Permissions:** Editor+ trong project chứa turbine
    """
    turbine_id = await _service.get_turbine_id_from_image(image_id)
    if not turbine_id:
        raise HTTPException(status_code=404, detail="Image không tồn tại")

    await check_turbine_access(turbine_id, current_user, min_role="editor")

    # đảm bảo đã có assessment do AI tạo trước đó
    existing = await database.fetch_one(
        sa.select(damage_assessments_table.c.id).where(damage_assessments_table.c.inspection_image_id == image_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Damage assessment không tồn tại")

    return await _service.update_assessment(image_id, request.dict(exclude_unset=True))


# ============= Optional: Image streaming =============

def iter_file(path: Path, chunk_size: int = 1024 * 1024):
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            yield chunk

@router.get("/images/{image_id}/stream")
async def stream_image(image_id: str):
    row = await database.fetch_one(
        inspection_images_table.select().where(inspection_images_table.c.id == image_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "image/jpeg"

    return StreamingResponse(
        iter_file(file_path),
        media_type=content_type,
        headers={"Content-Disposition": "inline"}
    )


@router.patch("/images/{image_id}/assessment/box", status_code=status.HTTP_200_OK)
async def partial_update_bounding_box(
    image_id: str,
    request: PartialUpdateBoxRequest,
    current_user: dict = Depends(require_user),
):
    """
    ✅ Cập nhật một hoặc nhiều field của MỘT bounding box cụ thể (partial update by index).
    
    **Use Cases:**
    - Chỉ sửa type (LV level) của 1 box
    - Chỉ sửa confidence của 1 box
    - Sửa nhiều field của 1 box cùng lúc
    - Không cần gửi lại toàn bộ array
    
    **Request Body Examples:**
    
    1. **Chỉ sửa type của box đầu tiên (index 0):**
    ```json
    {
      "box_index": 0,
      "updates": {
        "type": "LV_5"
      }
    }
    ```
    
    2. **Sửa type và confidence của box thứ 2 (index 1):**
    ```json
    {
      "box_index": 1,
      "updates": {
        "type": "LV_4",
        "confidence": 0.92
      }
    }
    ```
    
    3. **Sửa toạ độ của box thứ 3 (index 2):**
    ```json
    {
      "box_index": 2,
      "updates": {
        "x": 0.5000,
        "y": 0.4000,
        "width": 0.2000,
        "height": 0.3000
      }
    }
    ```
    
    **Request Fields:**
    - box_index (int, required): Index của box cần sửa (bắt đầu từ 0)
    - updates (object, required): Các field cần update
      - Allowed fields: x, y, width, height, type, confidence
      - Chỉ cần gửi field muốn sửa, các field khác giữ nguyên
    
    **Returns:**
    ```json
    {
      "message": "Cập nhật box index 0 thành công",
      "assessment": {
        "id": "assessment-uuid",
        "image_id": "image-uuid",
        "ai_bounding_boxes": [
          {"x": 0.6258, "y": 0.3321, "width": 0.6403, "height": 0.6395, "type": "LV_5", "confidence": 0.78},
          {"x": 0.1234, "y": 0.5678, "width": 0.2000, "height": 0.3000, "type": "LV_3", "confidence": 0.65}
        ],
        "updated_box_index": 0,
        "updated_box": {"x": 0.6258, "y": 0.3321, "width": 0.6403, "height": 0.6395, "type": "LV_5", "confidence": 0.78},
        "description": "User notes",
        "updated_at": "2025-10-23T09:15:00Z"
      }
    }
    ```
    
    **Errors:**
    - 400: box_index out of range
    - 400: Invalid field name in updates
    - 404: Assessment not found
    
    **Permissions:** Editor+ trong project chứa turbine
    """
    turbine_id = await _service.get_turbine_id_from_image(image_id)
    if not turbine_id:
        raise HTTPException(status_code=404, detail="Image không tồn tại")

    await check_turbine_access(turbine_id, current_user, min_role="editor")

    # Đảm bảo đã có assessment
    existing = await database.fetch_one(
        sa.select(damage_assessments_table.c.id).where(damage_assessments_table.c.inspection_image_id == image_id)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Damage assessment không tồn tại")

    return await _service.partial_update_bounding_box(
        image_id=image_id,
        box_index=request.box_index,
        field_updates=request.updates
    )


@router.get("/images/{image_id}/processed")
async def stream_processed_image_placeholder(
    image_id: str,
    current_user: dict = Depends(require_user),
):
    # FE hãy vẽ bbox theo JSON trả từ /inspections/{inspection_id}/results
    raise HTTPException(status_code=404, detail="Processed image không được tạo. FE hãy vẽ bbox theo JSON.")
