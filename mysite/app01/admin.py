from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Profile, Department, LeaveRequest, ApprovalStep, OfficeSupply, SupplyRequest, RequestApproval, OfficeSupplyItem, OfficeSupplyOption

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'profile'
    fk_name = 'user'  # 指定使用 'user' 字段作为外键

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(Department)
admin.site.register(LeaveRequest)
admin.site.register(ApprovalStep)
admin.site.register(OfficeSupply)
admin.site.register(SupplyRequest)
admin.site.register(RequestApproval)
admin.site.register(OfficeSupplyItem)
admin.site.register(OfficeSupplyOption)
