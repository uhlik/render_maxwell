#!/Library/Frameworks/Python.framework/Versions/3.4/bin/python3
# -*- coding: utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import sys
import traceback
import json
import shutil
import argparse
import textwrap
import os

from pymaxwell import *


quiet = False
LOG_FILE_PATH = None


def log(msg, indent=0):
    if(quiet):
        return
    # print("{0}> {1}".format("    " * indent, msg))
    # logger.info("{0}> {1}".format("    " * indent, msg))
    m = "{0}> {1}".format("    " * indent, msg)
    print(m)
    if(LOG_FILE_PATH is not None):
        with open(LOG_FILE_PATH, mode='a', encoding='utf-8', ) as f:
            f.write("{}{}".format(m, "\n"))


class PercentDone():
    def __init__(self, total, prefix="> ", indent=0):
        self.current = 0
        self.percent = -1
        self.last = -1
        self.total = total
        self.prefix = prefix
        self.indent = indent
        self.t = "    "
        self.r = "\r"
        self.n = "\n"
    
    def step(self, numdone=1):
        if(quiet):
            return
        self.current += numdone
        self.percent = int(self.current / (self.total / 100))
        if(self.percent > self.last):
            sys.stdout.write(self.r)
            sys.stdout.write("{0}{1}{2}%".format(self.t * self.indent, self.prefix, self.percent))
            self.last = self.percent
        if(self.percent >= 100 or self.total == self.current):
            sys.stdout.write(self.r)
            # sys.stdout.write("{0}{1}{2}%{3}".format(self.t * self.indent, self.prefix, 100, self.n))
            # logger.info("{0}{1}{2}%".format(self.t * self.indent, self.prefix, 100))
            sys.stdout.write("{0}{1}{2}%{3}".format(self.t * self.indent, self.prefix, 100, self.n))
            if(LOG_FILE_PATH is not None):
                with open(LOG_FILE_PATH, mode='a', encoding='utf-8', ) as f:
                    f.write("{}".format("{0}{1}{2}%{3}".format(self.t * self.indent, self.prefix, 100, self.n)))


def get_objects_names(scene):
    it = CmaxwellObjectIterator()
    o = it.first(scene)
    l = []
    while not o.isNull():
        name, _ = o.getName()
        l.append(name)
        o = it.next()
    return l


def base_and_pivot(o):
    b, p, _ = o.getBaseAndPivot()
    o = b.origin
    x = b.xAxis
    y = b.yAxis
    z = b.zAxis
    rb = [[o.x(), o.y(), o.z()], [x.x(), x.y(), x.z()], [y.x(), y.y(), y.z()], [z.x(), z.y(), z.z()]]
    rp = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), )
    return rb, rp


def uncorrect_focal_length(step):
    flc = step[3]
    o = step[0]
    fp = step[1]
    d = Cvector()
    d.substract(fp, o)
    fd = d.norm()
    fluc = 1.0 / (1.0 / flc - 1 / fd)
    return fluc


def camera(c):
    v = c.getValues()
    s = c.getStep(0)
    o = s[0]
    f = s[1]
    u = s[2]
    r = {'name': v['name'],
         'shutter': 1.0 / v['shutter'],
         'iso': v['iso'],
         'x_res': v['xRes'],
         'y_res': v['yRes'],
         'pixel_aspect': v['pixelAspect'],
         'origin': (o.x(), o.y(), o.z()),
         'focal_point': (f.x(), f.y(), f.z()),
         'up': (u.x(), u.y(), u.z()),
         'focal_length': uncorrect_focal_length(s) * 1000.0,
         'f_stop': s[4],
         'film_width': round(v['filmWidth'] * 1000.0, 3),
         'film_height': round(v['filmHeight'] * 1000.0, 3),
         'active': False,
         'sensor_fit': None,
         'shift_x': 0.0,
         'shift_y': 0.0,
         'zclip': False,
         'zclip_near': 0.0,
         'zclip_far': 1000000.0,
         'type': 'CAMERA', }
    if(r['film_width'] > r['film_height']):
        r['sensor_fit'] = 'HORIZONTAL'
    else:
        r['sensor_fit'] = 'VERTICAL'
    cp = c.getCutPlanes()
    if(cp[2] is True):
        r['zclip'] = True
        r['zclip_near'] = cp[0]
        r['zclip_far'] = cp[1]
    sl = c.getShiftLens()
    r['shift_x'] = sl[0]
    r['shift_y'] = sl[1]
    d = c.getDiaphragm()
    r['diaphragm_type'] = d[0][0]
    r['diaphragm_angle'] = d[1]
    r['diaphragm_blades'] = d[2]
    return r


def object(o):
    is_instance, _ = o.isInstance()
    is_mesh, _ = o.isMesh()
    if(is_instance == 0 and is_mesh == 0):
        log("WARNING: only empties, meshes and instances are supported..", 2)
        return None
    r = {'name': o.getName()[0],
         'vertices': [],
         'normals': [],
         'triangles': [],
         'trianglesUVW': [],
         'matrix': (),
         'parent': None,
         'type': '',
         'materials': [],
         'nmats': 0,
         'matnames': [], }
    if(is_instance == 1):
        io = o.getInstanced()
        ion = io.getName()[0]
        b, p = base_and_pivot(o)
        r = {'name': o.getName()[0],
             'base': b,
             'pivot': p,
             'parent': None,
             'type': 'INSTANCE',
             'instanced': ion, }
        # no multi material instances, always one material per instance
        m, _ = o.getMaterial()
        if(m.isNull() == 1):
            r['material'] = None
        else:
            r['material'] = o.getName()
        p, _ = o.getParent()
        if(not p.isNull()):
            r['parent'] = p.getName()[0]
        
        cid, _ = o.getColorID()
        rgb8 = cid.toRGB8()
        col = [str(rgb8.r()), str(rgb8.g()), str(rgb8.b())]
        r['colorid'] = ", ".join(col)
        
        h = []
        if(o.getHideToCamera()):
            h.append("C")
        if(o.getHideToGI()):
            h.append("GI")
        if(o.getHideToReflectionsRefractions()):
            h.append("RR")
        r['hidden'] = ", ".join(h)
        
        return r
    # counts
    nv, _ = o.getVerticesCount()
    nn, _ = o.getNormalsCount()
    nt, _ = o.getTrianglesCount()
    nppv, _ = o.getPositionsPerVertexCount()
    ppv = 0
    if(nv > 0):
        r['type'] = 'MESH'
        
        cid, _ = o.getColorID()
        rgb8 = cid.toRGB8()
        col = [str(rgb8.r()), str(rgb8.g()), str(rgb8.b())]
        r['colorid'] = ", ".join(col)
        
        h = []
        if(o.getHideToCamera()):
            h.append("C")
        if(o.getHideToGI()):
            h.append("GI")
        if(o.getHideToReflectionsRefractions()):
            h.append("RR")
        r['hidden'] = ", ".join(h)
        
    else:
        r['type'] = 'EMPTY'
        
        cid, _ = o.getColorID()
        rgb8 = cid.toRGB8()
        col = [str(rgb8.r()), str(rgb8.g()), str(rgb8.b())]
        r['colorid'] = ", ".join(col)
        
    if(nppv - 1 != ppv and nv != 0):
        log("WARNING: only one position per vertex is supported..", 2)
    # vertices
    for i in range(nv):
        v, _ = o.getVertex(i, ppv)
        # (float x, float y, float z)
        r['vertices'].append((v.x(), v.y(), v.z()))
    # normals
    for i in range(nn):
        v, _ = o.getNormal(i, ppv)
        # (float x, float y, float z)
        r['normals'].append((v.x(), v.y(), v.z()))
    # triangles
    for i in range(nt):
        t = o.getTriangle(i)
        # (int v1, int v2, int v3, int n1, int n2, int n3)
        r['triangles'].append(t)
    # materials
    mats = []
    for i in range(nt):
        m, _ = o.getTriangleMaterial(i)
        if(m.isNull() == 1):
            n = None
        else:
            n = m.getName()
        if(n not in mats):
            mats.append(n)
        r['materials'].append((i, n))
    r['nmats'] = len(mats)
    r['matnames'] = mats
    # uv channels
    ncuv, _ = o.getChannelsUVWCount()
    for cuv in range(ncuv):
        # uv triangles
        r['trianglesUVW'].append([])
        for i in range(nt):
            t = o.getTriangleUVW(i, cuv)
            # float u1, float v1, float w1, float u2, float v2, float w2, float u3, float v3, float w3
            r['trianglesUVW'][cuv].append(t)
    # base and pivot to matrix
    b, p = base_and_pivot(o)
    r['base'] = b
    r['pivot'] = p
    # parent
    p, _ = o.getParent()
    if(not p.isNull()):
        r['parent'] = p.getName()[0]
    return r


def main(args):
    log("maxwell meshes to data:", 1)
    # scene
    mp = args.mxs_path
    log("reading mxs scene from: {0}".format(mp), 2)
    scene = Cmaxwell(mwcallback)
    ok = scene.readMXS(mp)
    if(not ok):
        if(not os.path.exists(mp)):
            raise RuntimeError("Error during reading scene {}, file not found..".format(mp))
        raise RuntimeError("Error during reading scene {}".format(mp))
    if(scene.isProtectionEnabled()):
        raise RuntimeError("Protected MXS ({})".format(mp))
    # objects
    nms = get_objects_names(scene)
    data = []
    if(args.objects):
        # objects to data
        log("converting empties, objects and instances..", 2)
        progress = PercentDone(len(nms), prefix="> ", indent=2, )
        for n in nms:
            d = None
            o = scene.getObject(n)
            d = object(o)
            if(d is not None):
                data.append(d)
            progress.step()
    if(args.cameras):
        # cameras to data
        log("converting cameras..", 2)
        nms = scene.getCameraNames()
        cams = []
        if(type(nms) == list):
            for n in nms:
                cams.append(scene.getCamera(n))
        for c in cams:
            d = camera(c)
            if(d is not None):
                data.append(d)
        # set active camera
        if(len(cams) > 1):
            # if there is just one camera, this behaves badly.
            # use it just when there are two or more cameras..
            active_cam = scene.getActiveCamera()
            active_cam_name = active_cam.getName()
            for o in data:
                if(o['type'] == 'CAMERA'):
                    if(o['name'] == active_cam_name):
                        o['active'] = True
        else:
            for o in data:
                if(o['type'] == 'CAMERA'):
                    o['active'] = True
    if(args.sun):
        # sun
        env = scene.getEnvironment()
        if(env.getSunProperties()[0] == 1):
            log("converting sun..", 2)
            if(env.getSunPositionType() == 2):
                v, _ = env.getSunDirection()
            else:
                v, _ = env.getSunDirectionUsedForRendering()
            d = {'name': "The Sun",
                 'xyz': (v.x(), v.y(), v.z()),
                 'type': 'SUN', }
            data.append(d)
    # save data
    log("serializing..", 2)
    p = args.scene_data_path
    with open("{0}.tmp".format(p), 'w', encoding='utf-8', ) as f:
        json.dump(data, f, skipkeys=False, ensure_ascii=False, indent=4, )
    if(os.path.exists(p)):
        os.remove(p)
    shutil.move("{0}.tmp".format(p), p)
    log("done.", 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=textwrap.dedent('''Make serialized data from Maxwell meshes and cameras'''),
                                     epilog='', formatter_class=argparse.RawDescriptionHelpFormatter, add_help=True, )
    parser.add_argument('-q', '--quiet', action='store_true', help='no logging except errors')
    parser.add_argument('-o', '--objects', action='store_true', help='read objects')
    parser.add_argument('-c', '--cameras', action='store_true', help='read cameras')
    parser.add_argument('-s', '--sun', action='store_true', help='read sun')
    parser.add_argument('log_file', type=str, help='path to log file')
    parser.add_argument('mxs_path', type=str, help='path to source .mxs')
    parser.add_argument('scene_data_path', type=str, help='path to serialized data')
    args = parser.parse_args()
    
    quiet = args.quiet
    LOG_FILE_PATH = args.log_file
    
    try:
        # import cProfile, pstats, io
        # pr = cProfile.Profile()
        # pr.enable()
        
        main(args)
        
        # pr.disable()
        # s = io.StringIO()
        # sortby = 'cumulative'
        # ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        # ps.print_stats()
        # print(s.getvalue())
        
    except Exception as e:
        import traceback
        m = traceback.format_exc()
        log(m)
        sys.exit(1)
    sys.exit(0)
