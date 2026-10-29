## Notes
This is a complete working starter/MVP. For production, add CSRF protection, stronger validation, encrypted/private ID-proof storage, admin verification, HTTPS, cloud/object storage, rate limiting, proper maps/geocoding, and email provider integration.


### Added: Provider/Customer WhatsApp + True Live GPS
- WhatsApp opens the registered phone number of the selected customer/provider.
- Provider live GPS uses browser `watchPosition()` and sends repeated coordinates.
- Socket.IO sends location updates to the booking participant.
- Customer map updates the provider marker live.
- GPS permission is required.
