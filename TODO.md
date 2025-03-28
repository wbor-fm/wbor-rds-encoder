# TODO

- [ ] Fall back to persona name and show title as `artist` and `title`, respectively, if the timeout for a song is reached
- [ ] Add a setting to disable the song timeout completely (`duration` from Spinitron will not be used - all RT+ packets will persist until the next is sent)
- [ ] Profanity and unidecoding do-not-notify and ignore lists (currently, `jerry` or `xx` are marked as profanity)
- [ ] Add a setting to disable the profanity filter completely
- [ ] If a RT+ packet has timed out, the `TEXT` field should also be cleared and something else should be sent (e.g. a bumper)
