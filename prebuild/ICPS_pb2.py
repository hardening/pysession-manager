# Generated by the protocol buffer compiler.  DO NOT EDIT!

from google.protobuf import descriptor
from google.protobuf import message
from google.protobuf import reflection
from google.protobuf import descriptor_pb2
# @@protoc_insertion_point(imports)



DESCRIPTOR = descriptor.FileDescriptor(
  name='ICPS.proto',
  package='freerds.icps',
  serialized_pb='\n\nICPS.proto\x12\x0c\x66reerds.icps\"`\n\x17\x41uthenticateUserRequest\x12\x11\n\tsessionId\x18\x01 \x02(\r\x12\x10\n\x08username\x18\x02 \x02(\t\x12\x10\n\x08password\x18\x03 \x02(\t\x12\x0e\n\x06\x64omain\x18\x04 \x02(\t\"\xd5\x01\n\x18\x41uthenticateUserResponse\x12\x46\n\nauthStatus\x18\x01 \x02(\x0e\x32\x32.freerds.icps.AuthenticateUserResponse.AUTH_STATUS\x12\x17\n\x0fserviceEndpoint\x18\x02 \x01(\t\"X\n\x0b\x41UTH_STATUS\x12\x14\n\x10\x41UTH_SUCCESSFULL\x10\x00\x12\x17\n\x13\x41UTH_BAD_CREDENTIAL\x10\x01\x12\x1a\n\x16\x41UTH_INVALID_PARAMETER\x10\x02* \n\x07MSGTYPE\x12\x15\n\x10\x41uthenticateUser\x10\xc8\x01')

_MSGTYPE = descriptor.EnumDescriptor(
  name='MSGTYPE',
  full_name='freerds.icps.MSGTYPE',
  filename=None,
  file=DESCRIPTOR,
  values=[
    descriptor.EnumValueDescriptor(
      name='AuthenticateUser', index=0, number=200,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=342,
  serialized_end=374,
)


AuthenticateUser = 200


_AUTHENTICATEUSERRESPONSE_AUTH_STATUS = descriptor.EnumDescriptor(
  name='AUTH_STATUS',
  full_name='freerds.icps.AuthenticateUserResponse.AUTH_STATUS',
  filename=None,
  file=DESCRIPTOR,
  values=[
    descriptor.EnumValueDescriptor(
      name='AUTH_SUCCESSFULL', index=0, number=0,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='AUTH_BAD_CREDENTIAL', index=1, number=1,
      options=None,
      type=None),
    descriptor.EnumValueDescriptor(
      name='AUTH_INVALID_PARAMETER', index=2, number=2,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=252,
  serialized_end=340,
)


_AUTHENTICATEUSERREQUEST = descriptor.Descriptor(
  name='AuthenticateUserRequest',
  full_name='freerds.icps.AuthenticateUserRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    descriptor.FieldDescriptor(
      name='sessionId', full_name='freerds.icps.AuthenticateUserRequest.sessionId', index=0,
      number=1, type=13, cpp_type=3, label=2,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='username', full_name='freerds.icps.AuthenticateUserRequest.username', index=1,
      number=2, type=9, cpp_type=9, label=2,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='password', full_name='freerds.icps.AuthenticateUserRequest.password', index=2,
      number=3, type=9, cpp_type=9, label=2,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='domain', full_name='freerds.icps.AuthenticateUserRequest.domain', index=3,
      number=4, type=9, cpp_type=9, label=2,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  extension_ranges=[],
  serialized_start=28,
  serialized_end=124,
)


_AUTHENTICATEUSERRESPONSE = descriptor.Descriptor(
  name='AuthenticateUserResponse',
  full_name='freerds.icps.AuthenticateUserResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    descriptor.FieldDescriptor(
      name='authStatus', full_name='freerds.icps.AuthenticateUserResponse.authStatus', index=0,
      number=1, type=14, cpp_type=8, label=2,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    descriptor.FieldDescriptor(
      name='serviceEndpoint', full_name='freerds.icps.AuthenticateUserResponse.serviceEndpoint', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=unicode("", "utf-8"),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _AUTHENTICATEUSERRESPONSE_AUTH_STATUS,
  ],
  options=None,
  is_extendable=False,
  extension_ranges=[],
  serialized_start=127,
  serialized_end=340,
)

_AUTHENTICATEUSERRESPONSE.fields_by_name['authStatus'].enum_type = _AUTHENTICATEUSERRESPONSE_AUTH_STATUS
_AUTHENTICATEUSERRESPONSE_AUTH_STATUS.containing_type = _AUTHENTICATEUSERRESPONSE;
DESCRIPTOR.message_types_by_name['AuthenticateUserRequest'] = _AUTHENTICATEUSERREQUEST
DESCRIPTOR.message_types_by_name['AuthenticateUserResponse'] = _AUTHENTICATEUSERRESPONSE

class AuthenticateUserRequest(message.Message):
  __metaclass__ = reflection.GeneratedProtocolMessageType
  DESCRIPTOR = _AUTHENTICATEUSERREQUEST
  
  # @@protoc_insertion_point(class_scope:freerds.icps.AuthenticateUserRequest)

class AuthenticateUserResponse(message.Message):
  __metaclass__ = reflection.GeneratedProtocolMessageType
  DESCRIPTOR = _AUTHENTICATEUSERRESPONSE
  
  # @@protoc_insertion_point(class_scope:freerds.icps.AuthenticateUserResponse)

# @@protoc_insertion_point(module_scope)
