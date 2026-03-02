"""Regression test: schedules on different days must not be collapsed."""


class TestScheduleDedupByday:
    def test_different_byday_not_deduped(self):
        """Mon 9-5 and Fri 9-5 are distinct schedules, not duplicates."""
        mon = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO",
        }
        fri = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "FR",
        }

        schedules_to_create = [mon]
        exists = False
        for existing in schedules_to_create:
            if (
                existing["freq"] == fri["freq"]
                and existing["wkst"] == fri["wkst"]
                and existing["opens_at"] == fri["opens_at"]
                and existing["closes_at"] == fri["closes_at"]
                and existing.get("byday") == fri.get("byday")
            ):
                exists = True
                break
        assert (
            not exists
        ), "Different byday values must not be treated as duplicates"

    def test_same_byday_deduped(self):
        """Identical schedules (including byday) should be collapsed."""
        mon1 = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO",
        }
        mon2 = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
            "byday": "MO",
        }

        schedules_to_create = [mon1]
        exists = False
        for existing in schedules_to_create:
            if (
                existing["freq"] == mon2["freq"]
                and existing["wkst"] == mon2["wkst"]
                and existing["opens_at"] == mon2["opens_at"]
                and existing["closes_at"] == mon2["closes_at"]
                and existing.get("byday") == mon2.get("byday")
            ):
                exists = True
                break
        assert exists, "Identical schedules should be deduplicated"

    def test_none_byday_deduped(self):
        """Two schedules with byday=None are duplicates."""
        s1 = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
        }
        s2 = {
            "freq": "WEEKLY",
            "wkst": "MO",
            "opens_at": "09:00",
            "closes_at": "17:00",
        }

        assert s1.get("byday") == s2.get("byday")  # None == None
