from django.contrib import admin
from .models import Company, CustomUser, ApprovalRule, ApprovalStep, Expense, ExpenseApproval

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'currency', 'created_at']
    search_fields = ['name', 'country']

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'company', 'manager']
    list_filter = ['role', 'company']
    search_fields = ['username', 'email']

@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'rule_type', 'is_manager_first', 'is_active']
    list_filter = ['rule_type', 'is_active', 'company']
    search_fields = ['name']

@admin.register(ApprovalStep)
class ApprovalStepAdmin(admin.ModelAdmin):
    list_display = ['approval_rule', 'approver', 'sequence']
    list_filter = ['approval_rule']
    ordering = ['approval_rule', 'sequence']

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['employee', 'amount', 'currency', 'category', 'status', 'expense_date']
    list_filter = ['status', 'category', 'company']
    search_fields = ['employee__username', 'description']
    date_hierarchy = 'expense_date'

@admin.register(ExpenseApproval)
class ExpenseApprovalAdmin(admin.ModelAdmin):
    list_display = ['expense', 'approver', 'status', 'step_number', 'approved_at']
    list_filter = ['status', 'step_number']
    search_fields = ['expense__description', 'approver__username']
