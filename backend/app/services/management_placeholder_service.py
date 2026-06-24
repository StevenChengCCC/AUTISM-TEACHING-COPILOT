class ManagementPlaceholderService:
    """Documents future management-system boundaries without implementing auth yet."""

    def capabilities(self) -> dict:
        return {
            "organizations": "Placeholder model for districts, clinics, or schools.",
            "teachers": "Placeholder model for staff identities.",
            "teacher_child_access": "Placeholder model for access permissions.",
            "curriculum_content": "Placeholder model for managed goal templates and curriculum assets.",
            "auth_status": "Not implemented in MVP.",
        }
