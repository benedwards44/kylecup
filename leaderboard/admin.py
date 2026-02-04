from django.contrib import admin
from . import models

class AthleteMonthSummaryInline(admin.TabularInline):
    model = models.AthleteMonthSummary
    extra = 0

@admin.register(models.Month)
class MonthAdmin(admin.ModelAdmin):
    list_display = ['slug', 'name']
    inlines = [AthleteMonthSummaryInline]


@admin.register(models.Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ['slug', 'name']
    inlines = [AthleteMonthSummaryInline]


@admin.register(models.Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['athlete_month_summary', 'distance', 'pace']