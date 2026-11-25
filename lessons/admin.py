from django.contrib import admin

from .models import (
    Assignment,
    Classroom,
    Exercise,
    ExerciseResult,
    Lesson,
    LessonProgress,
    Membership,
    Option,
    VocabItem,
)


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0


class ExerciseInline(admin.StackedInline):
    model = Exercise
    extra = 0
    show_change_link = True


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "level", "order", "published")
    list_filter = ("level", "published")
    inlines = [ExerciseInline]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("__str__", "lesson", "type", "trigger_seconds")
    list_filter = ("type", "lesson")
    inlines = [OptionInline]


admin.site.register(ExerciseResult)
admin.site.register(LessonProgress)
admin.site.register(VocabItem)

admin.site.register(Classroom)
admin.site.register(Membership)
admin.site.register(Assignment)
