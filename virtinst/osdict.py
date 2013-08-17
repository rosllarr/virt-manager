#
# List of OS Specific data
#
# Copyright 2006-2008  Red Hat, Inc.
# Jeremy Katz <katzj@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free  Software Foundation; either version 2 of the License, or
# (at your option)  any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301 USA.

from virtinst import support

_SENTINEL = -1234


class _SupportCheck(object):
    """
    Class for encapsulating complex support checks.

    Example: Fedora 18 supports virtio disks, but we only want to
    use virtio if the HV supports it. So this is initialized like:

    _SupportCheck(support.SUPPORT_CONN_HV_VIRTIO, "virtio")

    And that object should be passed to the diskbus value of _OSVariant.
    """
    def __init__(self, key, val):
        self._checks = []
        self.add_check(key, val)

    def add_check(self, key, val):
        self._checks.append((key, val))

    def check(self, conn, hv_type):
        for (support_key, value) in self._checks:
            if conn.check_conn_hv_support(support_key, hv_type):
                return value
        return _SENTINEL


_DISK_BUS_VIRTIO = _SupportCheck(support.SUPPORT_CONN_HV_VIRTIO, "virtio")
_NET_MODEL_VIRTIO = _SupportCheck(support.SUPPORT_CONN_HV_VIRTIO, "virtio")
_ACPI_OLD_XEN = _SupportCheck(support.SUPPORT_CONN_HV_SKIP_DEFAULT_ACPI, False)

_allvariants = {}


def lookup_os(key):
    ret = _allvariants.get(key)
    if ret is None:
        return ret
    return ret


def _sort(tosort, sortpref=None):
    sortby_mappings = {}
    distro_mappings = {}
    retlist = []
    sortpref = sortpref or []

    # Make sure we are sorting by 'sortby' if specified, and group distros
    # by their 'distro' tag first and foremost
    for key, osinfo in tosort.items():
        sortby = osinfo.sortby or key
        sortby_mappings[sortby] = key

        distro = osinfo.distro or "zzzzzzz"
        if distro not in distro_mappings:
            distro_mappings[distro] = []
        distro_mappings[distro].append(sortby)

    # We want returned lists to be sorted descending by 'distro', so we get
    # debian5, debian4, fedora14, fedora13
    #   rather than
    # debian4, debian5, fedora13, fedora14
    for distro_list in distro_mappings.values():
        distro_list.sort()
        distro_list.reverse()

    sorted_distro_list = distro_mappings.keys()
    sorted_distro_list.sort()
    sortpref.reverse()
    for prefer in sortpref:
        if not prefer in sorted_distro_list:
            continue
        sorted_distro_list.remove(prefer)
        sorted_distro_list.insert(0, prefer)

    for distro in sorted_distro_list:
        distro_list = distro_mappings[distro]
        for key in distro_list:
            orig_key = sortby_mappings[key]
            retlist.append(tosort[orig_key])

    return retlist


def list_os(list_types=False, typename=None,
            filtervars=None, only_supported=False,
            **kwargs):
    sortmap = {}
    filtervars = filtervars or []

    for key, osinfo in _allvariants.items():
        if list_types and not osinfo.is_type:
            continue
        if not list_types and osinfo.is_type:
            continue
        if typename and typename != osinfo.typename:
            continue
        if filtervars and osinfo.name not in filtervars:
            continue
        if only_supported and not osinfo.supported:
            continue
        sortmap[key] = osinfo
    return _sort(sortmap, **kwargs)


def lookup_osdict_key(conn, hv_type, variant, key, default):
    if variant is not None:
        val = getattr(_allvariants[variant], key)
        if isinstance(val, _SupportCheck):
            val = val.check(conn, hv_type)
    else:
        val = _SENTINEL
    if val == _SENTINEL:
        val = default
    return val


class _OSVariant(object):
    """
    Object tracking guest OS specific configuration bits.

    @name: name of the object. This must be lowercase. This becomes part of
        the virt-install command line API so we cannot remove any existing
        name (we could probably add aliases though)
    @label: Pretty printed label. This is used in the virt-manager UI.
        We can tweak this.
    @is_type: virt-install historically had a distinction between an
        os 'type' (windows, linux, etc), and an os 'variant' (fedora18,
        winxp, etc). Back in 2009 we actually required the user to
        specify --os-type if specifying an --os-variant even though we
        could figure it out easily. This distinction isn't needed any
        more, though it's still baked into the virt-manager UI where
        it is still pretty useful, so we fake it here. New types should
        not be added often.
    @parent: Name of a pre-created variant that we want to extend. So
        fedoraFOO would have parent fedoraFOO-1. It's used for inheiriting
        values.
    @sortby: A different key to use for sorting the distro list. By default
        it's 'name', so this doesn't need to be specified.
    @distro: This is a distro class. It's wired up in urlfetcher to give
        us a shortcut when detecting OS type from a URL.
    @supported: If this distro is supported by it's owning organization,
        like is it still receiving updates. We use this to limit the
        distros we show in virt-manager by default, so old distros aren't
        squeezing out current ones.
    @three_stage_install: If True, this VM has a 3 stage install, AKA windows.

    The rest of the parameters are about setting device/guest defaults
    based on the OS. They should be self explanatory. See guest.py for
    their usage.
    """
    def __init__(self, name, label, is_type=False,
                 sortby=None, parent=_SENTINEL,
                 distro=_SENTINEL, supported=_SENTINEL,
                 three_stage_install=_SENTINEL,
                 acpi=_SENTINEL, apic=_SENTINEL, clock=_SENTINEL,
                 netmodel=_SENTINEL, diskbus=_SENTINEL,
                 inputtype=_SENTINEL, inputbus=_SENTINEL,
                 videomodel=_SENTINEL):
        if is_type:
            if parent != _SENTINEL:
                raise RuntimeError("OS types must not specify parent")
            parent = None
        elif parent == _SENTINEL:
            raise RuntimeError("Must specify explicit parent")
        else:
            parent = _allvariants[parent]

        def _get_default(name, val, default=_SENTINEL):
            if val == _SENTINEL:
                if not parent:
                    return default
                return getattr(parent, name)
            return val

        if name != name.lower():
            raise RuntimeError("OS dictionary wants lowercase name, not "
                               "'%s'" % name)

        self.name = name
        self.label = label
        self.sortby = sortby

        self.is_type = bool(is_type)
        self.typename = _get_default("typename",
                                     self.is_type and self.name or _SENTINEL)

        # 'types' should rarely be altered, this check will make
        # doubly sure that a new type isn't accidentally added
        _approved_types = ["linux", "windows", "unix",
                           "solaris", "other"]
        if self.typename not in _approved_types:
            raise RuntimeError("type '%s' for variant '%s' not in list "
                               "of approved distro types %s" %
                               (self.typename, self.name, _approved_types))

        self.distro = _get_default("distro", distro, None)
        self.supported = _get_default("supported", supported, False)
        self.three_stage_install = _get_default("three_stage_install",
                                                three_stage_install)

        self.acpi = _get_default("acpi", acpi)
        self.apic = _get_default("apic", apic)
        self.clock = _get_default("clock", clock)

        self.netmodel = _get_default("netmodel", netmodel)
        self.videomodel = _get_default("videomodel", videomodel)
        self.diskbus = _get_default("diskbus", diskbus)
        self.inputtype = _get_default("inputtype", inputtype)
        self.inputbus = _get_default("inputbus", inputbus)


def _add_type(*args, **kwargs):
    kwargs["is_type"] = True
    _t = _OSVariant(*args, **kwargs)
    _allvariants[_t.name] = _t





def _add_var(*args, **kwargs):
    v = _OSVariant(*args, **kwargs)
    _allvariants[v.name] = v


_add_type("linux", "Linux")
_add_var("rhel2.1", "Red Hat Enterprise Linux 2.1", distro="rhel", parent="linux")
_add_var("rhel3", "Red Hat Enterprise Linux 3", parent="rhel2.1")
_add_var("rhel4", "Red Hat Enterprise Linux 4", supported=True, parent="rhel3")
_add_var("rhel5", "Red Hat Enterprise Linux 5", supported=False, parent="rhel4")
_add_var("rhel5.4", "Red Hat Enterprise Linux 5.4 or later", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="rhel5")
_add_var("rhel6", "Red Hat Enterprise Linux 6", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, inputtype="tablet", inputbus="usb", parent="rhel5.4")
_add_var("rhel7", "Red Hat Enterprise Linux 7", supported=False, parent="rhel6")

_add_var("fedora5", "Fedora Core 5", sortby="fedora05", distro="fedora", parent="linux")
_add_var("fedora6", "Fedora Core 6", sortby="fedora06", parent="fedora5")
_add_var("fedora7", "Fedora 7", sortby="fedora07", parent="fedora6")
_add_var("fedora8", "Fedora 8", sortby="fedora08", parent="fedora7")
# Apparently F9 has selinux errors when installing with virtio:
# https: //bugzilla.redhat.com/show_bug.cgi?id=470386
_add_var("fedora9", "Fedora 9", sortby="fedora09", netmodel=_NET_MODEL_VIRTIO, parent="fedora8")
_add_var("fedora10", "Fedora 10", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="fedora9")
_add_var("fedora11", "Fedora 11", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, inputtype="tablet", inputbus="usb", parent="fedora10")
_add_var("fedora12", "Fedora 12", parent="fedora11")
_add_var("fedora13", "Fedora 13", parent="fedora12")
_add_var("fedora14", "Fedora 14", parent="fedora13")
_add_var("fedora15", "Fedora 15", parent="fedora14")
_add_var("fedora16", "Fedora 16", parent="fedora15")
_add_var("fedora17", "Fedora 17", parent="fedora16")
_add_var("fedora18", "Fedora 18", supported=True, parent="fedora17")
_add_var("fedora19", "Fedora 19", parent="fedora18")
_add_var("fedora20", "Fedora 20", parent="fedora19")

_add_var("opensuse11", "openSuse 11", distro="suse", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="linux")
_add_var("opensuse12", "openSuse 12", parent="opensuse11")

_add_var("sles10", "Suse Linux Enterprise Server", distro="suse", supported=True, parent="linux")
_add_var("sles11", "Suse Linux Enterprise Server 11", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="sles10")

_add_var("mandriva2009", "Mandriva Linux 2009 and earlier", distro="mandriva", parent="linux")
_add_var("mandriva2010", "Mandriva Linux 2010 and later", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="mandriva2009")

_add_var("mes5", "Mandriva Enterprise Server 5.0", distro="mandriva", parent="linux")
_add_var("mes5.1", "Mandriva Enterprise Server 5.1 and later", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="mes5")

_add_var("mageia1", "Mageia 1 and later", distro="mageia", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, inputtype="tablet", inputbus="usb", parent="linux")

_add_var("altlinux", "ALT Linux", distro="altlinux", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, inputtype="tablet", inputbus="usb", parent="linux")

_add_var("debianetch", "Debian Etch", distro="debian", sortby="debian4", parent="linux")
_add_var("debianlenny", "Debian Lenny", sortby="debian5", supported=True, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="debianetch")
_add_var("debiansqueeze", "Debian Squeeze", sortby="debian6", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, inputtype="tablet", inputbus="usb", parent="debianlenny")
_add_var("debianwheezy", "Debian Wheezy", sortby="debian7", parent="debiansqueeze")

_add_var("ubuntuhardy", "Ubuntu 8.04 LTS (Hardy Heron)", distro="ubuntu", netmodel=_NET_MODEL_VIRTIO, parent="linux")
_add_var("ubuntuintrepid", "Ubuntu 8.10 (Intrepid Ibex)", parent="ubuntuhardy")
_add_var("ubuntujaunty", "Ubuntu 9.04 (Jaunty Jackalope)", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="ubuntuintrepid")
_add_var("ubuntukarmic", "Ubuntu 9.10 (Karmic Koala)", parent="ubuntujaunty")
_add_var("ubuntulucid", "Ubuntu 10.04 LTS (Lucid Lynx)", supported=True, parent="ubuntukarmic")
_add_var("ubuntumaverick", "Ubuntu 10.10 (Maverick Meerkat)", supported=False, parent="ubuntulucid")
_add_var("ubuntunatty", "Ubuntu 11.04 (Natty Narwhal)", parent="ubuntumaverick")
_add_var("ubuntuoneiric", "Ubuntu 11.10 (Oneiric Ocelot)", parent="ubuntunatty")
_add_var("ubuntuprecise", "Ubuntu 12.04 LTS (Precise Pangolin)", supported=True, parent="ubuntuoneiric")
_add_var("ubuntuquantal", "Ubuntu 12.10 (Quantal Quetzal)", parent="ubuntuprecise")
_add_var("ubunturaring", "Ubuntu 13.04 (Raring Ringtail)", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, videomodel="vmvga", parent="ubuntuquantal")
_add_var("ubuntusaucy", "Ubuntu 13.10 (Saucy Salamander)", parent="ubunturaring")

_add_var("generic24", "Generic 2.4.x kernel", parent="linux")
_add_var("generic26", "Generic 2.6.x kernel", parent="generic24")
_add_var("virtio26", "Generic 2.6.25 or later kernel with virtio", sortby="genericvirtio26", diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="generic26")


_add_type("windows", "Windows", clock="localtime", three_stage_install=True, inputtype="tablet", inputbus="usb", videomodel="vga")
_add_var("win2k", "Microsoft Windows 2000", sortby="mswin4", acpi=_ACPI_OLD_XEN, apic=_ACPI_OLD_XEN, parent="windows")
_add_var("winxp", "Microsoft Windows XP", sortby="mswin5", supported=True, acpi=_ACPI_OLD_XEN, apic=_ACPI_OLD_XEN, parent="windows")
_add_var("winxp64", "Microsoft Windows XP (x86_64)", supported=True, sortby="mswin564", parent="windows")
_add_var("win2k3", "Microsoft Windows Server 2003", supported=True, sortby="mswinserv2003", parent="windows")
_add_var("win2k8", "Microsoft Windows Server 2008", supported=True, sortby="mswinserv2008", parent="windows")
_add_var("vista", "Microsoft Windows Vista", supported=True, sortby="mswin6", parent="windows")
_add_var("win7", "Microsoft Windows 7", supported=True, sortby="mswin7", parent="windows")


_add_type("solaris", "Solaris", clock="localtime")
_add_var("solaris9", "Sun Solaris 9", parent="solaris")
_add_var("solaris10", "Sun Solaris 10", inputtype="tablet", inputbus="usb", parent="solaris")
# https://bugzilla.redhat.com/show_bug.cgi?id=894017 claims tablet doesn't work for solaris 11
_add_var("solaris11", "Sun Solaris 11", inputtype=None, inputbus=None, parent="solaris")
_add_var("opensolaris", "Sun OpenSolaris", inputtype="tablet", inputbus="usb", parent="solaris")

_add_type("unix", "UNIX")
# http: //www.nabble.com/Re%3A-Qemu%3A-bridging-on-FreeBSD-7.0-STABLE-p15919603.html
_add_var("freebsd6", "FreeBSD 6.x", netmodel="ne2k_pci", parent="unix")
_add_var("freebsd7", "FreeBSD 7.x", parent="freebsd6")
_add_var("freebsd8", "FreeBSD 8.x", supported=True, netmodel="e1000", parent="freebsd7")
_add_var("freebsd9", "FreeBSD 9.x", parent="freebsd8")
_add_var("freebsd10", "FreeBSD 10.x", supported=False, diskbus=_DISK_BUS_VIRTIO, netmodel=_NET_MODEL_VIRTIO, parent="freebsd9")

# http: //calamari.reverse-dns.net: 980/cgi-bin/moin.cgi/OpenbsdOnQemu
# https: //www.redhat.com/archives/et-mgmt-tools/2008-June/msg00018.html
_add_var("openbsd4", "OpenBSD 4.x", netmodel="pcnet", parent="unix")


_add_type("other", "Other")
_add_var("msdos", "MS-DOS", acpi=False, apic=False, parent="other")
_add_var("netware4", "Novell Netware 4", parent="other")
_add_var("netware5", "Novell Netware 5", parent="other")
_add_var("netware6", "Novell Netware 6", parent="other")
_add_var("generic", "Generic", supported=True, parent="other")
