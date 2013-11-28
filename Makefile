
SRC_PROTO=../FreeRds/server/FreeRDS/protocols/protobuf/

OUT_DIR=protobuf
protobuf_files: $(SRC_PROTO)/pbRPC.proto $(SRC_PROTO)/ICP.proto  $(SRC_PROTO)/ICPS.proto 
	protoc -I=$(SRC_PROTO) --python_out=. $^



all: protobuf_files

.PHONY: protobuf_files
