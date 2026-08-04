from django.db import models

class Solution(models.Model):
    length = models.IntegerField()
    segment_sizes = models.JSONField()
    blade_width = models.FloatField()
    obj_value = models.FloatField()
    solution = models.JSONField()

    def __str__(self):
        return f"Solution for length={self.length}, blade_width={self.blade_width}"
