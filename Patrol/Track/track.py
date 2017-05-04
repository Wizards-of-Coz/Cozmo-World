'''
Track is stored as graph structure. 
'''
import json
import random
import os
from Common.wocmath import tupleMagnitude, tupleRadians
from typing import List

TRACK_FILE_PATH = "track.json"
MAGIC_SCALE = 1.0

class Edge:

    def __init__(self, start, end):
        self.start = start
        self.end = end
        direction = (end.x - start.x, end.y - start.y)
        self.distance = tupleMagnitude(direction, direction)
        self.radians = tupleRadians(direction)

    # get one edge randomly that starts from the end vertex of current edge
    def randomNextEdge(self):
        edge = self.end.randomEdge()

        # avoid U turn
        while edge.end == self.start:
            edge = self.end.randomEdge()

        return edge

class Vertex:

    def __init__(self, id, x, y):
        self.id = id
        self.x = x * MAGIC_SCALE
        self.y = y * MAGIC_SCALE
        # blvd edge start at this vertex
        self.outEdges = []

    # record the edge *(objects)* which starts with this vertex
    def addEdge(self, edge: Edge):
        self.outEdges.append(edge)

    # get one random edge that starts from this vertex
    def randomEdge(self):
        if not self.outEdges:
            raise Exception("Initialization not finished")
        else:
            return random.choice(self.outEdges)

    # find the exact one edge that starts from this vertex and ends at vertex with endId
    def findOutEdge(self, endId):
        edge = next((e for e in self.outEdges if e.end.id == endId))
        return edge

    # find any one edge that starts from this vertex and NOT ends at vertex with endId
    def findOutEdgeNotEndsAt(self, endId):
        edge = next((e for e in self.outEdges if e.end.id != endId))
        return edge

class BldgVertex(Vertex):
    def __init__(self, id, x, y, d):
        super(BldgVertex, self).__init__(id, x, y)
        self.d = d * MAGIC_SCALE

class PoseTrack:

    def __init__(self, edge: Edge, speed):
        # used to test if route complete a circle
        self.initialEdge = edge

        self.edge = None
        self.switchEdge(edge, speed)

        self.edgeChanged = False
        self.angleDiff = 0.0
        self.angleAbs = 0.0
        self.distance = edge.distance
        self.routeEnd = False
        
    # set current edge to the edge object provided in the parameters
    # and modify other state variables consistently
    def switchEdge(self, edge: Edge, speed, offset = 0.0):
        # time passed moving on current edge
        self.movedTime = 0.0
        self.maxTime = (edge.distance + offset) / speed
        print("edge length: %s" % edge.distance)

        if self.edge:
            self.angleDiff = edge.radians - self.edge.radians
            self.angleAbs = edge.radians
        else:
            self.angleDiff = 0.0
            self.angleAbs = 0.0
        
        # the edge currently on
        self.edge = edge
        self.distance = edge.distance + offset

    # update the poseTrack with given speed and small time
    # set flags accordingly if current edge is passed 
    # (current version only update once when the edge is passed) 
    def update(self, deltaTime, speed):
        self.movedTime += deltaTime

        # when Cozmo passed current edge
        if self.movedTime > self.maxTime:
            self.edgeChanged = True
            # update edge
            edge = self.edge.randomNextEdge()
            self.switchEdge(edge, speed)

            if edge == self.initialEdge:
                self.routeEnd = True

    # read and reset edge change flag
    def consumeEdgeChangeSignal(self):
        if self.edgeChanged:
            self.edgeChanged = False
            return True
        else:
            return False

    # read and reset route end flag
    def consumeRouteEndSignal(self):
        if self.routeEnd:
            self.routeEnd = False
            return True
        else:
            return False

# a path consists of a list of vertex objects,
# and two flags indicating turning directions from/to small lanes to/from start and end vertex
class Path:
    # nodes: list of vertex *Id*
    # vertices: list of vertex *object*
    def __init__(self, nodes: List[str], vertices: List[Vertex]):
        self.nodes = []
        self.firstTurnLeft = True
        self.lastTurnRight = True
        for i in range(len(nodes)):
            nodeId = nodes[i]
            # if the nodeId is denoted as "-<vertex id>", 
            # it means the direction on big roads is not turn left from direction along the small lane
            if '-' in nodeId:
                nodeId = nodeId[1:]
                if i == 1:
                    self.firstTurnLeft = False
                elif i == len(nodes) - 1:
                    self.lastTurnRight = False
                else:
                    print("Invalid path in file")
            self.nodes.append(vertices[nodeId])

# pose track data structure specified with paths
class PathPoseTrack(PoseTrack):
    def __init__(self, path: Path, speed):
        self.setPath(path)
        v0 = path.nodes[0]
        v1 = path.nodes[1]
        e = v0.findOutEdge(v1.id)
        super(PathPoseTrack, self).__init__(e, speed)

    def update(self, deltaTime, speed):
        # Cozmo finishes current path
        if self.index >= self.length:
            return
        
        self.movedTime += deltaTime

        # when Cozmo passed current edge
        if self.movedTime > self.maxTime:
            self.edgeChanged = True
            # the current path node list is not exhausted
            if self.index < self.length - 2:
                edge = self.edge.end.findOutEdge(self.path.nodes[self.index + 2].id)
                self.switchEdge(edge, speed)
            # the current path node list reaches end
            elif self.index == self.length - 2:
                edge = self.edge.end.findOutEdgeNotEndsAt(self.edge.start.id)
                self.switchEdge(edge, speed)
                self.routeEnd = True

            self.index += 1

    def setPath(self, path: Path):
        self.index = 0
        self.path = path
        self.length = len(path.nodes)

    def updatePath(self, path: Path, speed, offset = 0.0):
        self.setPath(path)
        v0 = path.nodes[0]
        v1 = path.nodes[1]
        e = v0.findOutEdge(v1.id)
        self.switchEdge(e, speed, offset)

    # position correction detected with marker position offset
    def updateOffset(self, offset):
        self.distance = self.distance + offset
        
        

class Track:
    def __init__(self, path = TRACK_FILE_PATH):
        path = os.path.join(os.path.dirname(__file__), path)
        
        # vertexId -> vertex object
        self.vertices = {}
        # list of edge objects
        self.edges = []
        # (start vertexId, end vertexId) -> path object
        self.paths = {}

        d = None
        with open(path) as track_data:
            d = json.load(track_data)

        vertices = d["blvd"]["vertices"]
        for vertexData in vertices:
            v = Vertex(**vertexData)
            self.vertices[v.id] = v

        bldgVertices = d["bldg"]["vertices"]
        for vertexData in bldgVertices:
            v = BldgVertex(**vertexData)
            self.vertices[v.id] = v

        edges = d["blvd"]["edges"]
        edges.extend(d["bldg"]["edges"])
        for edgeData in edges:
            self.createEdgePair(**edgeData)

        routes = d["routes"]
        for pathData in routes:
            self.createPath(**pathData)

    def createEdgePair(self, start, end, oneway):
        startV = self.vertices[start]
        endV = self.vertices[end]

        e = Edge(startV, endV)
        self.edges.append(e)
        startV.addEdge(e)

        if not oneway:
            e2 = Edge(endV, startV)
            self.edges.append(e2)
            endV.addEdge(e2)

    def createPathPair(self, nodes):
        path = Path(nodes, self.vertices)
        path2 = Path(list(reversed(nodes)), self.vertices)
        self.storePath(path)
        self.storePath(path2)

    def createPath(self, nodes):
        path = Path(nodes, self.vertices)
        self.storePath(path)

    def storePath(self, path):
        # store this path
        if path.nodes[0].id not in self.paths:
            self.paths[path.nodes[0].id] = {}

        if path.nodes[-1].id not in self.paths[path.nodes[0].id]:
            self.paths[path.nodes[0].id][path.nodes[-1].id] = []

        self.paths[path.nodes[0].id][path.nodes[-1].id].append(path)

    def getEdge(self, index):
        return self.edges[index]

    def getPoseTrack(self, speed):
        return PoseTrack(self.edges[0], speed)

    def getPathPoseTrack(self, speed):
        return PathPoseTrack(self.paths["GA"]["PH"][0], speed)

    def getPath(self, start, end, second) -> Path:
        l = self.paths[start][end]
        # path = next((p for p in l if p.nodes[1].id == second), None)
        return l[0]

if __name__ == "__main__":
    Track()
