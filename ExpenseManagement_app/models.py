from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils import timezone

# --- Company Model ---
class Company(models.Model):
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    currency = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Companies"
    
    def __str__(self):
        return self.name or "Unnamed Company"


# --- Custom User ---
class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('employee', 'Employee'),
    ]

    groups = models.ManyToManyField(
        Group,
        related_name='expensemanagementapp_user_set',
        blank=True,
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='expensemanagementapp_user_permissions_set',
        blank=True,
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates'
    )
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # 🔹 Helper for Manager Dashboard
    def get_team_expenses(self):
        """Return all team expenses for manager or all company expenses for admin."""
        from .models import Expense
        if self.role == 'manager':
            return Expense.objects.filter(employee__manager=self)
        elif self.role == 'admin':
            return Expense.objects.filter(company=self.company)
        return Expense.objects.none()
    
    def get_pending_approvals(self):
        """Return expenses pending for this user’s approval."""
        from .models import ExpenseApproval
        return ExpenseApproval.objects.filter(approver=self, status='pending')


# --- Approval Workflow ---
class ApprovalRule(models.Model):
    RULE_TYPE_CHOICES = [
        ('sequential', 'Sequential Approval'),
        ('percentage', 'Percentage Rule'),
        ('specific', 'Specific Approver'),
        ('hybrid', 'Hybrid Rule'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='approval_rules')
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES)
    percentage_threshold = models.IntegerField(null=True, blank=True)
    specific_approver = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='specific_approval_rules'
    )
    is_manager_first = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"


class ApprovalStep(models.Model):
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, related_name='steps')
    approver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='approval_steps', null=True)
    sequence = models.IntegerField(help_text="Order of approval (1, 2, 3, etc.)")
    
    class Meta:
        ordering = ['sequence']
        unique_together = ['approval_rule', 'sequence']
    
    def __str__(self):
        username = self.approver.username if self.approver else "Unknown"
        return f"Step {self.sequence}: {username}"


# --- Expense Models ---
class Expense(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    CATEGORY_CHOICES = [
        ('travel', 'Travel'),
        ('food', 'Food & Dining'),
        ('office', 'Office Supplies'),
        ('transport', 'Transportation'),
        ('accommodation', 'Accommodation'),
        ('entertainment', 'Entertainment'),
        ('other', 'Other'),
    ]
    
    employee = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='expenses', null=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='expenses', null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, null=True, blank=True)
    amount_in_company_currency = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField()
    merchant_name = models.CharField(max_length=255, blank=True)
    expense_date = models.DateField()
    receipt_image = models.ImageField(upload_to='receipts/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.SET_NULL, null=True, blank=True)
    current_step = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        username = self.employee.username if self.employee else "Unknown"
        return f"{username} - {self.amount} {self.currency} - {self.category}"


class ExpenseApproval(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='approvals', null=True)
    approver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='expense_approvals', null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    comments = models.TextField(blank=True)
    step_number = models.IntegerField()
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['step_number']
        unique_together = ['expense', 'approver', 'step_number']
    
    def __str__(self):
        approver_name = self.approver.username if self.approver else "Unknown"
        return f"{self.expense} - {approver_name} ({self.status})"
    
    def save(self, *args, **kwargs):
        if self.status in ['approved', 'rejected'] and not self.approved_at:
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)
