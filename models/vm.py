from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from db.base_class import Base


class VM(Base):
    __tablename__ = "vms"

    id = Column(Integer, primary_key=True, index=True)
    vm_name = Column(String,index=True)
    os_type = Column(String)
    ip_address = Column(String, unique=True, nullable= True)
    status = Column(String, default="creating")

    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="vms")