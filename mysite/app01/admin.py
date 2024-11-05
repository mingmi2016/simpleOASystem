from django.contrib import admin
from .models import (
    # Profile, 
    # Department, 
    ApprovalStep, 
    OfficeSupply, 
    SupplyRequest, 
    RequestApproval, 
    SupplyRequestItem,
    # OfficeSupplyOption
)

# Register your models here.
# admin.site.register(Profile)
# admin.site.register(Department)
admin.site.register(ApprovalStep)
admin.site.register(OfficeSupply)
admin.site.register(SupplyRequest)
admin.site.register(RequestApproval)
admin.site.register(SupplyRequestItem)
# admin.site.register(OfficeSupplyOption)
