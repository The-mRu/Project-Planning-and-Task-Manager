from django.contrib import admin
from apps.users.models import User, Profile, OTPVerification
# Register your models here.
class ProfileInLine(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'profile'
    
# Modify this User admin for production use
class UserAdmin(admin.ModelAdmin):
    inlines = (ProfileInLine, )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    list_select_related = ('profile', )
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username', )
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.prefetch_related('profile')
        return queryset

    def profile_picture(self, instance):
        return instance.profile.profilePicture.url

    profile_picture.short_description = 'Profile Picture'
    
    def profile_picture_change_count(self, instance):
        return instance.profile.profile_picture_change_count

    profile_picture_change_count.short_description = 'Profile Picture Change Count'
    
    def profile_picture_change_count(self, instance):
        return instance.profile.profile_picture_change_count

    profile_picture_change_count.short_description = 'Profile Picture Change Count'
        
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'email', 'purpose', 'created_at', 'is_verified')
    search_fields = ('user__username', 'email')
    list_filter = ('purpose', 'is_verified')
    ordering = ('-created_at', )
    
    
admin.site.register(OTPVerification, OTPVerificationAdmin)
admin.site.register(User,UserAdmin)
admin.site.register(Profile)

