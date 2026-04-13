from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from celery.result import AsyncResult

from core.auth import get_current_user
from core.templates import templates
from core.config import settings
from schemas.vm_schema import VMCreate
from models.vm_model import VM
from models.user_model import User
from worker import create_vm_task_async, control_vm_task_async, delete_vm_task_async, celery_app
from crud import vm_crud

router = APIRouter()
ALLOWED_ACTIONS = {"start", "stop_soft", "stop_hard", "reboot_soft", "reboot_hard"}

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
      "vms" : vms,
      "max" : settings.MAX_VM_PER_USER
      }
  )

# ─────────────────────────────────────────
# 2. 신규 VM 생성 요청 (비동기 태스크 할당)
# ─────────────────────────────────────────
@router.post("/create-vm")
async def create_vm(
  payload: VMCreate,
  db: Session = Depends(get_db),
  current_user: str = Depends(get_current_user)
):
  # ─── 1. 사용자 확인 ───
  user = db.query(User).filter(User.username == current_user).first()
  if not user:
      raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

  # ─── 2. 사용자당 VM 개수 제한 체크 ───
  vm_count = vm_crud.count_vms_by_owner(db, owner_id=user.id)
  if vm_count >= settings.MAX_VM_PER_USER:
      raise HTTPException(
          status_code=429,
          detail=f"VM은 최대 {settings.MAX_VM_PER_USER}개까지 생성할 수 있습니다."
      )

  # ─── 3. Celery 비동기 작업 호출 ───
  task = create_vm_task_async.delay(user.id, payload.os_type)

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

  # ─── 1. action 화이트리스트 검증 ───
  if action not in ALLOWED_ACTIONS:
      raise HTTPException(status_code=400, detail="허용되지 않은 명령입니다.")

  # ─── 2. 권한 및 세션 검증 ───
  user = db.query(User).filter(User.username == username).first()

  if not user:
    raise HTTPException(
      status_code=404,
      detail="인증되지 않은 사용자이거나 세션이 만료되었습니다."
    )

  # ─── 3. VM 소유권 확인 ───
  vm = db.query(VM).filter(VM.id == vm_id, VM.owner_id == user.id).first()

  if not vm:
    raise HTTPException(
      status_code=403,
      detail="권한이 없습니다."
    )
  
  # ─── 4. 중복 작업 방지 (상태 체크) ───
  busy_states = ["processing", "starting", "stopping", "rebooting", "creating"]
  if vm.status in busy_states:
    raise HTTPException(
      status_code=400,
      detail="작업이 진행 중입니다. 잠시만 기다려주세요."
    )

  # ─── 5. 상태 업데이트 및 비동기 명령 전송 ───
  vm_crud.update_vm_status(db, vm_id, "processing")
  control_vm_task_async.delay(vm_id, action, user.id)

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
  task = delete_vm_task_async.delay(vm_id, user.id)

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

# ──────────────────────────────────────────────────────────────────────
# 6. VM 생성 태스크 결과 조회 (폴링용)
# ──────────────────────────────────────────────────────────────────────
@router.get("/vm/task/{task_id}")
async def get_task_result(
  task_id: str,
  db: Session = Depends(get_db),
  username: str = Depends(get_current_user)
):
  """
  Celery 태스크 완료 여부 및 결과 조회.
  VM 생성 완료 시 private_key를 1회 반환하고 이후 삭제.
  """
  result = AsyncResult(task_id, app=celery_app)
  
  # ─── 아직 진행 중 ───
  if not result.ready():
    return {"status" : "pending"}
  
  # ─── 실패 ───
  if result.failed():
    return {"status" : "error" , "message" : "Vm 생성실패"}
  
  # ─── 성공 ───
  data = result.result
  if not isinstance(data, dict):
    return {"status": "error", "message": "알 수 없는 오류"}
  
  if data.get("status") == "success" and "private_key" in data:
    private_key = data.pop("private_key")
    vm_id = data.get("vm_id")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
      raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    
    vm = db.query(VM).filter(VM.id == vm_id, VM.owner_id == user.id).first()
    if not vm:
      raise HTTPException(status_code=403, detail="권한이 없습니다.")
    
    # ─── 태스크 결과에서 private_key 제거 (1회성) ───
    result.forget()
    return {
      "status": "success",
      "private_key": private_key,
      "vm_id" : vm_id
    }
    
  return {"status": "error", "message": data.get("message", "알 수 없는 오류")}