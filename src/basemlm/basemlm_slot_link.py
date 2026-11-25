from src.basemlm.basemlm_link import BaseMlmLink
from src.basemlm.basemlm_slot import BaseMlmSlot


class BaseMlmSlotLink(BaseMlmSlot):

    def __init__(self, slot_name: str, value: str, link: BaseMlmLink, is_source_end: bool):
        """The value of a SlotLink is always the full name of an existing object,
        allowing to retrieve it within the context of a model"""
        super().__init__(slot_name, value.split("::")[2])
        # value only returns short name of object, may lead to problems if name is reused in other slots
        self.slot_category = "SLOT-LINK"
        self.links: [BaseMlmLink] = []
        self.add_link(link)
        self.is_source_end = is_source_end

    def get_links(self) -> [BaseMlmLink]:
        return self.links

    def add_link(self, link: BaseMlmLink):
        self.links.append(link)

    def get_attribute(self):
        if self.is_source_end:
            return self.links[0].get_association().get_source_association_end()
        else:
            return self.links[0].get_association().get_target_association_end()