from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from core.auth import get_current_user
from core.templates import templates
from schemas.vm_schema import VMCreate
from models.vm_model import VM
from models.user_model import User
from worker import create_vm_task_async, control_vm_task_async, delete_vm_task_async
from crud import vm_crud

router = APIRouter()

# ────────────────────────────
# 1. 대시보드 페이지 렌더링
# ────────────────────────────
@router.get("/dashboard")
async def dashboard_page(
  request: Request,
  db: Session = Depends(get_db),
  username: str = Depends(get_current_user)
  ):
  # ─── 1. 사용자 확인 ───
  user = db.query(User).filter(User.username == username).first()

  if not user:
    raise HTTPException(
      status_code=404,
      detail="사용자를 찾을 수 없습니다."
    )

  # ─── 2. 소유한 VM 목록 조회 ───
  vms = db.query(VM).filter(VM.owner_id == user.id).order_by(VM.id.desc()).all()

  return templates.TemplateResponse(
    request=request,
    name="dashboard.html",
    context={
      "request": request, 
      "username": user.username,
      "vms" : vms
      }
  )

# ─────────────────────────────────────────
# 2. 신규 VM 생성 요청 (비동기 태스크 할당)
# ─────────────────────────────────────────
@router.post("/create-vm")
async def create_vm(
  payload: VMCreate,
  current_user: str = Depends(get_current_user)
):
  # ─── Celery 비동기 작업 호출 ───
  task = create_vm_task_async.delay(current_user, payload.os_type)

  return {
    "status": "success",
    "message": f"{payload.os_type} VM 생성이 시작되었습니다.",
    "task_id": task.id
  }

# ──────────────────────────────────────────
# 3. VM 전원 및 제어 (Start/Stop/Reboot 등)
# ──────────────────────────────────────────
@router.post("/vm/{vm_id}/control")
async def vm_control(
  vm_id: int,
  action: str,
  db: Session = Depends(get_db),
  username: str = Depends(get_current_user)
):
  # ─── 1. 권한 및 세션 검증 ───
  user = db.query(User).filter(User.username == username).first()

  if not user:
    raise HTTPException(
      status_code=404,
      detail="인증되지 않은 사용자이거나 세션이 만료되었습니다."
    )

  # ─── 2. VM 소유권 확인 ───
  vm = db.query(VM).filter(VM.id == vm_id, VM.owner_id == user.id).first()

  if not vm:
    raise HTTPException(
      status_code=403,
      detail="권한이 없습니다."
    )
  
  # ─── 3. 중복 작업 방지 (상태 체크) ───
  busy_states = ["processing", "starting", "stopping", "rebooting", "creating"]
  if vm.status in busy_states:
    raise HTTPException(
      status_code=400,
      detail="작업이 진행 중입니다. 잠시만 기다려주세요."
    )

  # ─── 4. 상태 업데이트 및 비동기 명령 전송 ───
  vm_crud.update_vm_status(db, vm_id, "processing")
  control_vm_task_async.delay(vm_id, action)

  return {"status": "success", "message": "명령이 대기열에 등록되었습니다."}


# ──────────────────────────────────────────────────────────
# 4. VM 삭제 요청 (강제 종료 → 폴더 삭제 → IP 회수 비동기)
# ──────────────────────────────────────────────────────────
@router.delete("/vm/{vm_id}")
async def delete_vm(
  vm_id: int,
  db: Session = Depends(get_db),
  username: str = Depends(get_current_user)
):
  # ─── 1. 사용자 세션 검증 ───
  user = db.query(User).filter(User.username == username).first()

  if not user:
    raise HTTPException(
      status_code=404,
      detail="인증되지 않은 사용자이거나 세션이 만료되었습니다."
    )

  # ─── 2. VM 소유권 확인 ───
  vm = db.query(VM).filter(VM.id == vm_id, VM.owner_id == user.id).first()

  if not vm:
    raise HTTPException(
      status_code=403,
      detail="권한이 없거나 존재하지 않는 VM입니다."
    )

  # ─── 3. 이미 삭제 진행 중인지 체크 ───
  busy_states = ["processing", "starting", "stopping", "rebooting", "creating", "deleting"]
  if vm.status in busy_states:
    raise HTTPException(
      status_code=400,
      detail="작업이 진행 중입니다. 완료 후 삭제해주세요."
    )

  # ─── 4. 비동기 삭제 태스크 등록 ───
  vm_crud.update_vm_status(db, vm_id, "deleting")
  task = delete_vm_task_async.delay(vm_id)

  return {
    "status": "success",
    "message": "VM 삭제가 시작되었습니다.",
    "task_id": task.id
  }

# ────────────────────────────────────────────
# 5. 실시간 VM 상태 목록 조회 (Polling용 API)
# ────────────────────────────────────────────
@router.get("/vms/status-list")
async def get_vms_status(
  db: Session = Depends(get_db),
  username: str=Depends(get_current_user)
):
  # ─── 1. 사용자 확인 ───
  user = db.query(User).filter(User.username == username).first()

  if not user:
    raise HTTPException(
      status_code=401,
      detail="인증되지 않은 사용자이거나 세션이 만료되었습니다."
    )

  # ─── 2. 최신 DB 상태 반영 및 목록 생성 ───
  db.expire_all()
  vms = db.query(VM).filter(VM.owner_id == user.id).all()

  return [
    {"id": v.id, "status": v.status} for v in vms
  ]